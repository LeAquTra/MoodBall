import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { MicCapture } from '../audio/capture'
import { playAudio, playCue, unlockAudio } from '../audio/ttsPlayer'
import { VoiceSocket, type VoiceEvent } from '../audio/voiceSocket'
import { useBallStore } from './ball'
import { useChatStore } from './chat'
import { useSettingsStore } from './settings'
import { useUiStore } from './ui'

export type VoiceState =
  | 'idle'
  | 'arming'
  | 'armed'
  | 'triggered'
  | 'listening'
  | 'thinking'
  | 'acting'
  | 'speaking'
  | 'error'

export const useVoiceStore = defineStore('voice', () => {
  const ui = useUiStore()
  const ball = useBallStore()
  const chat = useChatStore()
  const settingsStore = useSettingsStore()

  const state = ref<VoiceState>('idle')
  const lastText = ref('')
  const partial = ref('')
  const level = ref(0)
  const muted = ref(false)
  const error = ref('')
  const active = ref(false)
  const wakeWord = ref('小d小d')

  let socket: VoiceSocket | null = null
  let capture: MicCapture | null = null
  let commandBusy = false
  let pingTimer = 0
  let stateTimer = 0
  let partialTimer = 0

  const busy = computed(() => state.value === 'thinking' || state.value === 'acting' || state.value === 'speaking')
  const listening = computed(() => ['armed', 'triggered', 'listening'].includes(state.value))
  const statusText = computed(() => {
    switch (state.value) {
      case 'idle':
        return '点击麦克风开始'
      case 'arming':
        return '连接语音服务…'
      case 'armed':
        return '在听，说「小d小d」唤醒'
      case 'triggered':
        return '唤醒成功'
      case 'listening':
        return '我在听'
      case 'thinking':
        return '思考中…'
      case 'acting':
        return '处理中…'
      case 'speaking':
        return '正在说'
      case 'error':
        return error.value || '语音不可用'
    }
  })

  function setState(next: VoiceState, emotion?: string) {
    state.value = next
    if (emotion) ball.applyEmotion(emotion, 'state')
  }

  function clearStateTimer() {
    if (stateTimer) {
      window.clearTimeout(stateTimer)
      stateTimer = 0
    }
  }

  function clearPartialTimer() {
    if (partialTimer) {
      window.clearTimeout(partialTimer)
      partialTimer = 0
    }
  }

  async function start(): Promise<boolean> {
    if (active.value && socket?.isOpen()) return true
    if (active.value) await teardown()
    error.value = ''
    muted.value = false
    active.value = true
    setState('arming', '05')
    await unlockAudio()

    const wake =
      settingsStore.settings?.wake_word ||
      settingsStore.meta?.wake_word ||
      '小d小d'
    wakeWord.value = wake

    capture = new MicCapture()
    try {
      await capture.start((frame) => {
        level.value = frame.level
        if (socket?.isOpen() && !muted.value) socket.sendPcm(frame.buffer)
      })
    } catch (err) {
      handleMicFailure(err)
      return false
    }

    socket = new VoiceSocket({
      onEvent: handleEvent,
      onOpen: () => {
        setState('arming')
      },
      onClose: (clean) => {
        if (!clean && active.value) {
          error.value = '语音连接已断开，正在重连…'
          setState('error', '34')
        }
      },
      onError: (message) => {
        error.value = message
        setState('error', '34')
        ui.notify(message, 'error')
      },
    })

    try {
      await socket.connect({
        conversation_id: chat.currentId,
        wake_word: wake,
        mode: 'continuous',
      })
    } catch (err) {
      error.value = (err as Error).message
      setState('error', '34')
      ui.notify(error.value, 'error')
      await teardown()
      return false
    }

    window.clearInterval(pingTimer)
    pingTimer = window.setInterval(() => socket?.ping(), 20000)
    return true
  }

  function handleMicFailure(err: unknown) {
    const name = (err as DOMException)?.name || ''
    if (name === 'NotAllowedError' || name === 'SecurityError') {
      error.value = '麦克风权限被拒绝。请在站点设置里允许麦克风后重试。'
    } else if (name === 'NotFoundError') {
      error.value = '没有找到麦克风设备。'
    } else {
      error.value = `麦克风启动失败：${(err as Error).message || err}`
    }
    setState('error', '38')
    ui.notify(error.value, 'error')
    active.value = false
    void teardown(false)
  }

  async function stop(): Promise<void> {
    await teardown()
    setState('idle', '02')
    lastText.value = ''
    partial.value = ''
    level.value = 0
  }

  async function teardown(resetActive = true) {
    window.clearInterval(pingTimer)
    pingTimer = 0
    clearStateTimer()
    clearPartialTimer()
    socket?.stop()
    socket = null
    await capture?.stop()
    capture = null
    commandBusy = false
    if (resetActive) active.value = false
    level.value = 0
  }

  async function toggle(): Promise<void> {
    if (active.value) await stop()
    else await start()
  }

  function toggleMute() {
    muted.value = !muted.value
    socket?.mute(muted.value)
    ui.notify(muted.value ? '麦克风已静音' : '麦克风已恢复', 'info')
  }

  async function pttStart() {
    if (!active.value) {
      const ok = await start()
      if (!ok) return
    }
    await unlockAudio()
    socket?.pttStart()
    setState('listening', '35')
  }

  function pttStop() {
    socket?.pttStop()
    setState('thinking', '30')
  }

  function handleEvent(event: VoiceEvent) {
    switch (event.type) {
      case 'ready': {
        setState('armed', '35')
        break
      }
      case 'asr_status': {
        const status = String(event.state || '')
        if (status === 'connecting') {
          setState('arming', '05')
        } else if (status === 'error' || status === 'closed' || status === 'disabled') {
          error.value = String(event.message || 'ASR 服务不可用')
          setState('error', '34')
          ui.notify(error.value, 'warning')
        }
        break
      }
      case 'phase': {
        const value = String(event.value || '')
        if (value === 'armed') {
          if (!commandBusy) {
            clearPartialTimer()
            partial.value = ''
            setState('armed', '35')
            socket?.mute(false)
          }
        } else if (value === 'listening') {
          setState('listening', '35')
        } else if (value === 'thinking') {
          setState('thinking', '30')
        } else if (value === 'speaking') {
          setState('speaking', '39')
        } else if (value === 'idle') {
          setState('idle', '02')
        }
        break
      }
      case 'wake': {
        clearStateTimer()
        setState('triggered', '01')
        void playCue('wake')
        const remainder = String(event.remainder || '')
        if (remainder) lastText.value = remainder
        stateTimer = window.setTimeout(() => {
          if (state.value === 'triggered') setState('listening', '35')
        }, 240)
        break
      }
      case 'partial': {
        if (commandBusy || ['thinking', 'acting', 'speaking', 'error'].includes(state.value)) return
        partial.value = String(event.text || '')
        if (state.value === 'armed') setState('listening', '35')
        clearPartialTimer()
        partialTimer = window.setTimeout(() => {
          if (!commandBusy && state.value === 'listening') {
            partial.value = ''
            setState('armed', '35')
          }
        }, 2200)
        break
      }
      case 'final': {
        clearPartialTimer()
        const text = String(event.text || '').trim()
        partial.value = ''
        if (!text) {
          setState('armed', '35')
          return
        }
        lastText.value = text
        void handleCommand(text)
        break
      }
      case 'speech_start': {
        if (state.value === 'armed') setState('listening', '35')
        break
      }
      case 'speech_end': {
        if (state.value === 'listening') setState('thinking', '30')
        break
      }
      case 'error': {
        error.value = String(event.message || '语音服务返回错误')
        setState('error', '34')
        ui.notify(error.value, 'error')
        break
      }
      default:
        break
    }
  }

  async function handleCommand(text: string) {
    if (commandBusy) return
    if (chat.streaming) {
      ui.notify('上一轮还在生成，请稍等。', 'warning')
      setState('armed', '35')
      return
    }
    commandBusy = true
    setState('thinking', '30')
    socket?.mute(true)
    let audioPlayed = false
    let finished = false

    const finish = (delayMs = 300) => {
      if (finished) return
      finished = true
      window.setTimeout(() => {
        commandBusy = false
        socket?.mute(false)
        if (state.value === 'error') return
        setState('armed', '35')
      }, delayMs)
    }

    const speak = settingsStore.settings?.speak_replies ?? true
    const sent = await chat.sendMessage(text, {
      speak,
      handlers: {
        onState: (payload) => {
          if (payload.state === 'acting') setState('acting', '32')
          else if (payload.state === 'thinking') setState('thinking', '30')
        },
        onEmotion: (payload) => {
          if (payload.tips) ball.setTips(payload.tips)
        },
        onAudio: (url) => {
          audioPlayed = true
          setState('speaking', '39')
          void playAudio(url, () => finish(300))
        },
        onDone: () => {
          if (!audioPlayed) finish(250)
        },
        onError: () => {
          setState('error', '34')
          finish(1200)
        },
      },
    })

    if (!sent) finish(200)
  }

  return {
    state,
    lastText,
    partial,
    level,
    muted,
    error,
    active,
    wakeWord,
    busy,
    listening,
    statusText,
    start,
    stop,
    toggle,
    toggleMute,
    pttStart,
    pttStop,
    setState,
  }
})
