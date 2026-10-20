import { detectWake, extractWakeRemainder } from './wake'

export interface VoskCallbacks {
  onWake: (heard: string, remainder: string) => void
  onCommand: (text: string) => void
  onCommandTimeout: () => void
}

const MODEL_URL = `${import.meta.env.BASE_URL}models/model.tar.gz`
const COMMAND_TIMEOUT = 8000

type Phase = 'wake' | 'command'

/**
 * 离线识别会话：Vosk 模型 + 麦克风 + 持续识别。
 * - wake 阶段：partial/final 结果里匹配唤醒词
 * - command 阶段：拿下一句 final 作为指令，8 秒无结果则超时
 *
 * 模型加载一次后常驻（stop 只关麦克风），dispose 才会释放。
 */
export class VoskSession {
  private model: any = null
  private recognizer: any = null
  private context: AudioContext | null = null
  private stream: MediaStream | null = null
  private source: MediaStreamAudioSourceNode | null = null
  private processor: ScriptProcessorNode | null = null
  private callbacks: VoskCallbacks | null = null
  private phase: Phase = 'wake'
  private timer = 0
  private resetTimer = 0
  private alive = false
  private muted = false

  async start(callbacks: VoskCallbacks): Promise<void> {
    this.callbacks = callbacks
    this.alive = true
    this.muted = false

    try {
      if (!this.model) {
        const Vosk = await import('vosk-browser')
        this.model = await Vosk.createModel(MODEL_URL)
      }
      if (!this.alive) return

      await this.openMicrophone()
      if (!this.alive) {
        this.stop()
        return
      }

      this.phase = 'wake'
      this.createRecognizer()
    } catch (error) {
      this.stop()
      throw error
    }
  }

  setMuted(muted: boolean) {
    this.muted = muted
  }

  backToWake() {
    this.phase = 'wake'
    this.clearTimer()
    this.scheduleRecognizerReset()
  }

  stop() {
    this.alive = false
    this.clearTimer()
    window.clearTimeout(this.resetTimer)

    try {
      this.recognizer?.remove()
    } catch {
      /* 已经移除 */
    }
    this.recognizer = null

    this.processor?.disconnect()
    this.source?.disconnect()
    this.processor = null
    this.source = null

    this.stream?.getTracks().forEach((track) => track.stop())
    this.stream = null

    if (this.context && this.context.state !== 'closed') void this.context.close()
    this.context = null
  }

  dispose() {
    this.stop()
    try {
      this.model?.terminate()
    } catch {
      /* 已经释放 */
    }
    this.model = null
  }

  private async openMicrophone() {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    })
    this.stream = stream

    const context = new AudioContext({ sampleRate: 16000 })
    this.context = context
    if (context.state === 'suspended') await context.resume()

    if (context.sampleRate !== 16000) {
      stream.getTracks().forEach((track) => track.stop())
      this.stream = null
      void context.close()
      this.context = null
      throw new Error(`SAMPLE_RATE_${context.sampleRate}`)
    }

    const source = context.createMediaStreamSource(stream)
    const processor = context.createScriptProcessor(4096, 1, 1)

    processor.onaudioprocess = (event) => {
      if (!this.alive || this.muted || !this.recognizer) return
      try {
        this.recognizer.acceptWaveform(event.inputBuffer)
      } catch (error) {
        console.warn('[arouse] vosk acceptWaveform failed', error)
      }
    }

    // ScriptProcessor 必须接到 destination 才会被驱动，用 0 增益静音
    const mute = context.createGain()
    mute.gain.value = 0
    source.connect(processor)
    processor.connect(mute)
    mute.connect(context.destination)

    this.source = source
    this.processor = processor
  }

  private createRecognizer() {
    if (!this.model) return

    try {
      this.recognizer?.remove()
    } catch {
      /* 已经移除 */
    }

    const recognizer = new this.model.KaldiRecognizer(16000)

    recognizer.on('partialresult', (message: any) => {
      if (!this.alive || this.phase !== 'wake') return
      const partial = message?.result?.partial ?? ''
      if (detectWake(partial)) this.handleWake(partial)
    })

    recognizer.on('result', (message: any) => {
      if (!this.alive) return
      const text = message?.result?.text ?? ''
      this.handleFinal(text)
    })

    this.recognizer = recognizer
  }

  private handleFinal(text: string) {
    if (this.phase === 'command') {
      this.clearTimer()
      this.phase = 'wake'
      this.scheduleRecognizerReset()

      if (text.trim()) this.callbacks?.onCommand(text)
      else this.callbacks?.onCommandTimeout()
      return
    }

    if (detectWake(text)) this.handleWake(text)
  }

  private handleWake(heard: string) {
    this.phase = 'command'
    this.clearTimer()
    this.scheduleRecognizerReset()

    this.callbacks?.onWake(heard, extractWakeRemainder(heard))

    this.timer = window.setTimeout(() => {
      if (!this.alive) return
      this.phase = 'wake'
      this.scheduleRecognizerReset()
      this.callbacks?.onCommandTimeout()
    }, COMMAND_TIMEOUT)
  }

  private scheduleRecognizerReset() {
    window.clearTimeout(this.resetTimer)
    // 不能在 recognizer 自己的回调里同步 remove，推迟到下一个宏任务
    this.resetTimer = window.setTimeout(() => {
      if (this.alive) this.createRecognizer()
    }, 0)
  }

  private clearTimer() {
    window.clearTimeout(this.timer)
    this.timer = 0
  }
}
