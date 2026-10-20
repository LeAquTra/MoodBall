import { unlockAudio } from './context'

export interface MicFrame {
  buffer: ArrayBuffer
  level: number
}

export class MicCapture {
  private stream?: MediaStream
  private ctx?: AudioContext
  private node?: AudioWorkletNode
  private source?: MediaStreamAudioSourceNode
  private sink?: GainNode
  private onFrame?: (frame: MicFrame) => void
  private running = false

  async start(onFrame: (frame: MicFrame) => void): Promise<void> {
    if (this.running) return
    this.onFrame = onFrame
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('当前浏览器不支持麦克风采集，请使用最新版 Chrome / Edge。')
    }

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    })

    const ctx = await unlockAudio()
    if (!ctx) throw new Error('浏览器不支持 WebAudio。')
    this.ctx = ctx
    await ctx.audioWorklet.addModule(new URL('./pcm16-worklet.js', import.meta.url))
    if (ctx.state === 'suspended') await ctx.resume()

    this.node = new AudioWorkletNode(ctx, 'pcm16-framer', {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      outputChannelCount: [1],
      processorOptions: { targetRate: 16000, frameSize: 320 },
    })
    this.node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      const buffer = event.data
      const samples = new Int16Array(buffer)
      let sum = 0
      for (let i = 0; i < samples.length; i++) {
        const value = samples[i] / 32768
        sum += value * value
      }
      const rms = Math.sqrt(sum / Math.max(1, samples.length))
      const level = Math.max(0, Math.min(1, rms * 5))
      this.onFrame?.({ buffer, level })
    }

    this.source = ctx.createMediaStreamSource(this.stream)
    this.sink = ctx.createGain()
    this.sink.gain.value = 0
    this.source.connect(this.node)
    this.node.connect(this.sink)
    this.sink.connect(ctx.destination)
    this.running = true
  }

  async stop(): Promise<void> {
    this.running = false
    try {
      this.node?.port.close()
      this.node?.disconnect()
      this.source?.disconnect()
      this.sink?.disconnect()
    } catch {
      /* ignore */
    }
    this.stream?.getTracks().forEach((track) => track.stop())
    this.stream = undefined
    this.node = undefined
    this.source = undefined
    this.sink = undefined
    this.onFrame = undefined
  }

  isRunning(): boolean {
    return this.running
  }
}
