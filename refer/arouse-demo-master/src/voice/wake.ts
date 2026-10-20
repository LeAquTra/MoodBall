import { normalize } from '../lib/text'
import { getRecognitionCtor, speechSupported } from './speech'

/**
 * 唤醒词「小d小d」的识别变体。
 * Vosk 会把 xiao-di 听成「小弟 / 小滴 / 小丁 / 小 的」等，所以用字符集匹配
 * 「小 X 小 Y」，而不是死磕某一种写法。
 */
const WAKE_CHARS = '弟滴迪低底地第丁d的'
const WAKE_PATTERN = new RegExp(`小[${WAKE_CHARS}]小[${WAKE_CHARS}]`)
const WAKE_GREETINGS = ['你好小d', '嗨小d', '你好小滴', '你好小弟']

export function detectWake(text: string): boolean {
  const value = normalize(text)
  if (!value) return false
  // 只看结尾 16 个字符，避免连续说话时整句过长导致漏检
  const tail = value.slice(-16)
  return WAKE_PATTERN.test(tail) || WAKE_GREETINGS.some((item) => tail.includes(item))
}

/** 用户一口气说「小d小d 切换主题」时，取出唤醒词后面的指令 */
export function extractWakeRemainder(text: string): string {
  const value = normalize(text)
  const match = WAKE_PATTERN.exec(value)
  if (match) return value.slice(match.index + match[0].length)

  for (const greeting of WAKE_GREETINGS) {
    const index = value.indexOf(greeting)
    if (index >= 0) return value.slice(index + greeting.length)
  }
  return ''
}

export type WakeErrorCode = 'MIC_DENIED' | 'NETWORK' | 'UNKNOWN'

export interface WakeOptions {
  onWake: (heard: string) => void
  onError?: (code: WakeErrorCode) => void
}

/**
 * Web Speech 持续监听（Vosk 不可用时的回退）。
 * Chrome 的 continuous 模式会被静音自动打断，所以 onend 之后带退避地重启。
 */
export class WakeListener {
  private recognition: any = null
  private running = false
  private restartTimer = 0
  private restartDelay = 300
  private buffer = ''

  constructor(private readonly options: WakeOptions) {}

  get active(): boolean {
    return this.running
  }

  start() {
    if (this.running || !speechSupported) return
    this.running = true
    this.restartDelay = 300
    this.spawn()
  }

  stop() {
    this.running = false
    window.clearTimeout(this.restartTimer)
    if (this.recognition) {
      try {
        this.recognition.abort()
      } catch {
        /* 已经结束 */
      }
      this.recognition = null
    }
  }

  private spawn() {
    const Ctor = getRecognitionCtor()
    if (!Ctor || !this.running) return

    const recognition = new Ctor()
    this.recognition = recognition
    this.buffer = ''

    recognition.lang = 'zh-CN'
    recognition.continuous = true
    recognition.interimResults = true
    recognition.maxAlternatives = 1

    recognition.onresult = (event: any) => {
      if (!this.running) return

      let text = ''
      for (let i = 0; i < event.results.length; i += 1) {
        text += event.results[i][0].transcript
      }
      this.buffer = text.slice(-40)
      this.restartDelay = 300

      if (detectWake(this.buffer)) {
        const heard = this.buffer
        this.stop()
        this.options.onWake(heard)
      }
    }

    recognition.onerror = (event: any) => {
      console.warn('[arouse] wake speech error:', event.error)
      if (event.error === 'no-speech' || event.error === 'aborted') return

      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        this.running = false
        this.options.onError?.('MIC_DENIED')
        return
      }

      if (event.error === 'network') {
        this.running = false
        this.options.onError?.('NETWORK')
        return
      }

      this.options.onError?.('UNKNOWN')
    }

    recognition.onend = () => {
      this.recognition = null
      if (!this.running) return
      this.restartTimer = window.setTimeout(() => this.spawn(), this.restartDelay)
      this.restartDelay = Math.min(this.restartDelay * 1.6, 4000)
    }

    try {
      recognition.start()
    } catch {
      /* 已经在识别中 */
    }
  }
}
