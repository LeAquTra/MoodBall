import { reactive } from 'vue'
import { getAudioContext, unlockAudio } from './context'

export { unlockAudio } from './context'

export const ttsState = reactive({
  playing: false,
  error: '',
  lastUrl: '',
})

let currentSource: AudioBufferSourceNode | null = null
let currentToken = 0
let currentEnded: (() => void) | null = null
let endTimer = 0

export async function playAudio(url: string, onEnded?: () => void): Promise<void> {
  // 先停止上一条并清空回调，再取新 token；若顺序反过来，stopAudio 会让 token 失配。
  stopAudio(false)
  const token = ++currentToken
  ttsState.lastUrl = url
  ttsState.error = ''
  const ctx = await unlockAudio()
  if (!ctx) {
    ttsState.error = '浏览器不支持 WebAudio'
    onEnded?.()
    return
  }
  try {
    const response = await fetch(url)
    if (!response.ok) throw new Error(`音频加载失败（${response.status}）`)
    const arrayBuffer = await response.arrayBuffer()
    if (token !== currentToken) return
    const audioBuffer = await ctx.decodeAudioData(arrayBuffer)
    if (token !== currentToken) return
    const source = ctx.createBufferSource()
    source.buffer = audioBuffer
    source.connect(ctx.destination)
    currentSource = source
    currentEnded = onEnded ?? null
    ttsState.playing = true
    let completed = false
    const complete = () => {
      if (completed || token !== currentToken) return
      completed = true
      if (endTimer) {
        window.clearTimeout(endTimer)
        endTimer = 0
      }
      ttsState.playing = false
      currentSource = null
      const callback = currentEnded
      currentEnded = null
      callback?.()
    }
    source.onended = complete
    // 某些无声卡 / suspended AudioContext 环境不会触发 onended；
    // 用音频时长兜底，保证语音 FSM 一定能从 speaking 回到 armed。
    endTimer = window.setTimeout(complete, Math.round(audioBuffer.duration * 1000) + 600)
    source.start()
  } catch (error) {
    if (token === currentToken) {
      ttsState.playing = false
      ttsState.error = (error as Error).message
      const callback = currentEnded
      currentEnded = null
      callback?.()
    }
  }
}

export function stopAudio(notify = true): void {
  currentToken += 1
  if (endTimer) {
    window.clearTimeout(endTimer)
    endTimer = 0
  }
  if (currentSource) {
    try {
      currentSource.onended = null
      currentSource.stop()
      currentSource.disconnect()
    } catch {
      /* ignore */
    }
    currentSource = null
  }
  ttsState.playing = false
  if (notify) {
    const callback = currentEnded
    currentEnded = null
    callback?.()
  } else {
    currentEnded = null
  }
}

export async function playCue(kind: 'wake' | 'error' | 'done' = 'wake'): Promise<void> {
  const ctx = await unlockAudio()
  if (!ctx) return
  const oscillator = ctx.createOscillator()
  const gain = ctx.createGain()
  const now = ctx.currentTime
  const frequencies = kind === 'wake' ? [660, 880] : kind === 'error' ? [220, 180] : [520, 780]
  oscillator.type = 'sine'
  oscillator.frequency.setValueAtTime(frequencies[0], now)
  oscillator.frequency.exponentialRampToValueAtTime(frequencies[1], now + 0.14)
  gain.gain.setValueAtTime(0.0001, now)
  gain.gain.exponentialRampToValueAtTime(0.12, now + 0.02)
  gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.22)
  oscillator.connect(gain)
  gain.connect(ctx.destination)
  oscillator.start(now)
  oscillator.stop(now + 0.24)
  oscillator.onended = () => {
    oscillator.disconnect()
    gain.disconnect()
  }
}

export function audioContextState(): string {
  return getAudioContext()?.state ?? 'closed'
}
