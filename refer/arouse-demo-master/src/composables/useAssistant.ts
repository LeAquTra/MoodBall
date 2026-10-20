import { computed, ref } from 'vue'
import { matchCommand, type CommandDef, type CommandResult } from '../commands'
import { notify, pushLog, ttsEnabled } from '../store'
import {
  cancelSpeech,
  listenOnce,
  playCue,
  speak,
  speechSupported,
  unlockAudio,
  warmUpTts,
} from '../voice/speech'
import { WakeListener, type WakeErrorCode } from '../voice/wake'
import { VoskSession } from '../voice/vosk'
import type { CommandEffect, InputMode, VoiceState } from '../types'

type Engine = 'vosk' | 'webspeech' | 'keyboard'

const STATE_TEXT: Record<VoiceState, string> = {
  idle: '待命',
  arming: '初始化',
  armed: '聆听中',
  triggered: '已唤醒',
  listening: '请说指令',
  thinking: '处理中',
  speaking: '播报中',
  error: '异常',
}

const STATE_CODE: Record<VoiceState, string> = {
  idle: 'IDLE',
  arming: 'ARMING',
  armed: 'ARMED',
  triggered: 'WAKED',
  listening: 'LISTEN',
  thinking: 'THINK',
  speaking: 'SPEAK',
  error: 'ERROR',
}

const state = ref<VoiceState>('idle')
const engine = ref<Engine>('vosk')
const mode = ref<InputMode>('voice')
const lastUserText = ref('')
const focusSignal = ref(0)

let wake: WakeListener | null = null
let vosk: VoskSession | null = null
let voskActive = false
let disposed = false
let busy = false
/**
 * 会话令牌：开麦 / 关麦都会 +1。
 * 异步流程（加载模型、识别、播报）回来时若令牌已变，说明用户中途关了语音，
 * 直接丢弃结果，避免「关了麦克风又被自动重新打开」。
 */
let session = 0

const stateText = computed(() => STATE_TEXT[state.value])
const stateCode = computed(() => STATE_CODE[state.value])

const wait = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms))

function ensureWake(): WakeListener {
  if (!wake) {
    wake = new WakeListener({
      onWake: (heard) => {
        void handleSpeechWake(heard)
      },
      onError: (code) => handleWakeError(code),
    })
  }
  return wake
}

function handleWakeError(code: WakeErrorCode) {
  wake?.stop()

  if (code === 'MIC_DENIED') {
    state.value = 'error'
    pushLog('system', '麦克风权限被拒绝')
    notify('麦克风权限被拒绝，请在地址栏的站点设置里允许后重试')
    return
  }

  engine.value = 'keyboard'
  mode.value = 'keyboard'
  state.value = 'armed'
  pushLog('system', '识别服务不可用，切换到键盘演示模式')
  notify(
    code === 'NETWORK'
      ? '识别服务连不上（浏览器内置识别依赖厂商云服务），已切键盘模式'
      : '识别服务异常（详情见控制台），已切键盘模式',
  )
}

function isPermissionDenied(error: unknown): boolean {
  const name = (error as DOMException)?.name ?? ''
  return name === 'NotAllowedError' || name === 'SecurityError'
}

function isDeviceMissing(error: unknown): boolean {
  return (error as DOMException)?.name === 'NotFoundError'
}

async function startVosk(id: number) {
  if (!vosk) vosk = new VoskSession()

  await vosk.start({
    onWake: (heard, remainder) => handleVoskWake(heard, remainder),
    onCommand: (text) => handleVoskCommand(text),
    onCommandTimeout: () => handleCommandTimeout(),
  })

  if (id !== session) {
    vosk.stop()
    return
  }

  voskActive = true
  engine.value = 'vosk'
  mode.value = 'voice'
}

async function arm() {
  if (state.value === 'armed' || state.value === 'arming') return

  disposed = false
  session += 1
  const id = session

  mode.value = 'voice'
  state.value = 'arming'

  await warmUpTts()
  if (id !== session) return

  unlockAudio()

  try {
    await startVosk(id)
    if (id !== session) return
    state.value = 'armed'
    pushLog('system', '离线语音已就绪 · 说「小d小d」唤醒')
    notify('离线语音已就绪（Vosk 本地识别）')
    return
  } catch (error) {
    console.warn('[arouse] vosk unavailable:', error)
    if (id !== session) return

    if (isPermissionDenied(error)) {
      state.value = 'error'
      pushLog('system', '麦克风权限被拒绝')
      notify('麦克风权限被拒绝，请在站点设置中允许后重试')
      return
    }

    if (isDeviceMissing(error)) {
      state.value = 'error'
      pushLog('system', '没有检测到麦克风')
      notify('没有检测到麦克风设备')
      return
    }
  }

  if (speechSupported) {
    engine.value = 'webspeech'
    mode.value = 'voice'
    ensureWake().start()
    state.value = 'armed'
    pushLog('system', '离线模型不可用，已切换到浏览器识别')
    notify('离线模型不可用，已切换到浏览器识别')
    return
  }

  engine.value = 'keyboard'
  mode.value = 'keyboard'
  state.value = 'armed'
  pushLog('system', '没有可用的语音引擎，进入键盘演示模式')
  notify('键盘模式：按 F2 模拟唤醒')
}

function disarm() {
  session += 1
  vosk?.stop()
  voskActive = false
  wake?.stop()
  wake = null
  cancelSpeech()
  busy = false
  state.value = 'idle'
  pushLog('system', '语音已关闭')
  notify('语音已关闭')
}

function toggle() {
  if (state.value === 'idle' || state.value === 'error') void arm()
  else disarm()
}

function resumeWake() {
  if (disposed) return

  if (engine.value === 'vosk' && voskActive) {
    vosk?.backToWake()
  } else if (engine.value === 'webspeech' && speechSupported) {
    ensureWake().start()
  }

  state.value = 'armed'
}

async function respond(text: string, resume: boolean, token: number) {
  state.value = 'thinking'
  await wait(180)
  if (token !== session) return

  if (ttsEnabled.value) {
    state.value = 'speaking'
    vosk?.setMuted(true)
    await speak(text)
    vosk?.setMuted(false)
    if (token !== session) return
  }

  if (!resume || disposed) {
    state.value = 'idle'
    return
  }

  resumeWake()
}

function handleVoskWake(heard: string, remainder: string) {
  if (state.value !== 'armed' || busy) return

  const token = session
  lastUserText.value = heard
  state.value = 'triggered'
  pushLog('system', '唤醒词命中')
  playCue()

  if (remainder) {
    busy = true
    window.setTimeout(() => {
      busy = false
      if (token === session) void execute(remainder, token, true)
    }, 180)
    return
  }

  window.setTimeout(() => {
    if (token === session && state.value === 'triggered') state.value = 'listening'
  }, 220)
}

function handleVoskCommand(text: string) {
  if (disposed || state.value === 'idle') return
  void execute(text, session, true)
}

function handleCommandTimeout() {
  if (state.value === 'listening' || state.value === 'triggered') {
    state.value = 'armed'
    notify('没有听清，再说一次')
  }
}

async function handleSpeechWake(heard: string) {
  if (state.value !== 'armed' || busy) return

  const token = session
  wake?.stop()
  lastUserText.value = heard
  state.value = 'triggered'
  pushLog('system', '唤醒词命中')
  playCue()

  await wait(220)
  if (token !== session) return

  if (engine.value === 'keyboard') {
    focusInput()
    return
  }

  busy = true
  state.value = 'listening'
  const said = await listenOnce({ timeout: 8000 })

  if (token !== session) {
    busy = false
    return
  }

  if (!said) {
    busy = false
    notify('没有听清，再说一次')
    resumeWake()
    return
  }

  state.value = 'triggered'
  busy = false
  await execute(said, token)
}

async function execute(raw: string, token = session, force = false) {
  const text = raw.trim()
  if (!text) return
  if (!force && (busy || state.value === 'listening')) return

  const wasActive = state.value !== 'idle' && state.value !== 'error'
  lastUserText.value = text
  pushLog('user', text)

  let reply: CommandResult
  let commandId: string | undefined

  const hit = matchCommand(text)
  if (hit) {
    reply = hit.command.run()
    commandId = hit.command.id
  } else {
    reply = { reply: `还没有「${text}」这条指令。说「指令列表」，我告诉你都能做什么。` }
  }

  pushLog('assistant', reply.reply, commandId)
  applyEffects(reply.effects)

  const stopAfter = reply.effects?.includes('stop-voice') ?? false
  if (stopAfter) {
    vosk?.stop()
    voskActive = false
    wake?.stop()
    wake = null
  }

  busy = true
  try {
    await respond(reply.reply, wasActive && !stopAfter, token)
  } finally {
    busy = false
  }
}

async function invoke(command: CommandDef) {
  if (busy) return

  const token = session
  const wasActive = state.value !== 'idle' && state.value !== 'error'

  pushLog('user', `〔按钮〕${command.title}`)

  const result = command.run()
  pushLog('assistant', result.reply, command.id)
  applyEffects(result.effects)

  const stopAfter = result.effects?.includes('stop-voice') ?? false
  if (stopAfter) {
    vosk?.stop()
    voskActive = false
    wake?.stop()
    wake = null
  }

  busy = true
  try {
    await respond(result.reply, wasActive && !stopAfter, token)
  } finally {
    busy = false
  }
}

function simulateWake() {
  if (state.value === 'idle' || state.value === 'error') {
    notify('先点击麦克风开启语音')
    return
  }
  if (state.value !== 'armed') return

  wake?.stop()
  state.value = 'triggered'
  playCue()
  focusInput()
  notify('已模拟唤醒，输入一条指令')
}

function applyEffects(effects: CommandEffect[] = []) {
  for (const effect of effects) {
    if (effect === 'focus-input') focusInput()
    if (effect === 'scroll-commands') {
      document.getElementById('commands')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
    if (effect === 'scroll-top') window.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

function focusInput() {
  focusSignal.value += 1
}

function dispose() {
  session += 1
  disposed = true
  vosk?.dispose()
  vosk = null
  voskActive = false
  wake?.stop()
  wake = null
  cancelSpeech()
  busy = false
  state.value = 'idle'
}

export function useAssistant() {
  return {
    state,
    engine,
    mode,
    stateText,
    stateCode,
    lastUserText,
    focusSignal,
    speechSupported,
    arm,
    disarm,
    toggle,
    simulateWake,
    execute,
    invoke,
    focusInput,
    dispose,
  }
}
