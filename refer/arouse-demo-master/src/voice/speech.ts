/**
 * 浏览器语音能力的薄封装：
 * - listenOnce：单次识别（命令态）
 * - speak：TTS 播报
 * - playCue：唤醒提示音
 *
 * 说明：Web Speech API 的识别在 Chrome 上由浏览器厂商的在线服务完成，
 * 本 Demo 只保证「指令执行」发生在前端。
 */

type RecognitionCtor = new () => any

export function getRecognitionCtor(): RecognitionCtor | null {
  const scope = window as any
  return (scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null) as RecognitionCtor | null
}

export const speechSupported = typeof window !== 'undefined' && Boolean(getRecognitionCtor())

export interface ListenOptions {
  timeout?: number
  lang?: string
}

export function listenOnce(options: ListenOptions = {}): Promise<string> {
  const Ctor = getRecognitionCtor()
  if (!Ctor) return Promise.resolve('')

  const timeout = options.timeout ?? 8000
  const lang = options.lang ?? 'zh-CN'

  return new Promise<string>((resolve) => {
    const recognition = new Ctor()
    let settled = false
    let timer = 0

    const finish = (text: string) => {
      if (settled) return
      settled = true
      window.clearTimeout(timer)
      try {
        recognition.stop()
      } catch {
        /* 已经结束 */
      }
      resolve(text)
    }

    recognition.lang = lang
    recognition.continuous = false
    recognition.interimResults = false
    recognition.maxAlternatives = 1

    recognition.onresult = (event: any) => {
      let text = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        text += event.results[i][0].transcript
      }
      finish(text.trim())
    }

    recognition.onerror = (event: any) => {
      console.warn('[arouse] command speech error:', event.error)
      finish('')
    }
    recognition.onend = () => finish('')

    timer = window.setTimeout(() => finish(''), timeout)

    try {
      recognition.start()
    } catch {
      finish('')
    }
  })
}

let audioContext: AudioContext | null = null

export function unlockAudio() {
  if (!audioContext) {
    const Ctor = window.AudioContext ?? (window as any).webkitAudioContext
    if (Ctor) audioContext = new Ctor()
  }
  if (audioContext?.state === 'suspended') void audioContext.resume()
}

export function playCue() {
  unlockAudio()
  if (!audioContext) return

  const context = audioContext
  const oscillator = context.createOscillator()
  const gain = context.createGain()

  oscillator.type = 'sine'
  oscillator.frequency.setValueAtTime(880, context.currentTime)
  gain.gain.setValueAtTime(0.0001, context.currentTime)
  gain.gain.exponentialRampToValueAtTime(0.12, context.currentTime + 0.012)
  gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.14)

  oscillator.connect(gain).connect(context.destination)
  oscillator.start()
  oscillator.stop(context.currentTime + 0.16)
}

export function cancelSpeech() {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
}

export function warmUpTts(): Promise<void> {
  if (!('speechSynthesis' in window)) return Promise.resolve()
  if (window.speechSynthesis.getVoices().length) return Promise.resolve()

  return new Promise((resolve) => {
    let settled = false
    const done = () => {
      if (settled) return
      settled = true
      window.speechSynthesis.onvoiceschanged = null
      resolve()
    }
    window.speechSynthesis.onvoiceschanged = done
    window.setTimeout(done, 1200)
  })
}

export function speak(text: string, lang = 'zh-CN'): Promise<void> {
  if (!('speechSynthesis' in window) || !text.trim()) return Promise.resolve()

  return new Promise((resolve) => {
    const synth = window.speechSynthesis
    synth.cancel()

    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = lang
    utterance.rate = 1.02
    utterance.pitch = 1

    const voice = synth.getVoices().find((item) => item.lang.toLowerCase().startsWith('zh'))
    if (voice) utterance.voice = voice

    let settled = false
    let timer = 0

    const finish = () => {
      if (settled) return
      settled = true
      window.clearTimeout(timer)
      resolve()
    }

    timer = window.setTimeout(finish, Math.max(4000, text.length * 240))
    utterance.onend = finish
    utterance.onerror = finish
    synth.speak(utterance)
  })
}
