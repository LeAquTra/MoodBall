class PCM16Framer extends AudioWorkletProcessor {
  constructor(options) {
    super()
    const opts = options.processorOptions || {}
    this.frameSize = opts.frameSize || 320
    this.step = sampleRate / (opts.targetRate || 16000)
    this.phase = 0
    this.prev = 0
    this.cur = 0
    this.started = false
    this.out = new Int16Array(this.frameSize)
    this.write = 0
  }

  emit(sample) {
    const value = Math.max(-1, Math.min(1, sample))
    this.out[this.write++] = value < 0 ? value * 0x8000 : value * 0x7fff
    if (this.write === this.frameSize) {
      const buffer = this.out.buffer
      this.port.postMessage(buffer, [buffer])
      this.out = new Int16Array(this.frameSize)
      this.write = 0
    }
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0]
    if (!channel) return true
    for (let i = 0; i < channel.length; i++) {
      this.cur = channel[i]
      if (!this.started) {
        this.prev = this.cur
        this.started = true
        continue
      }
      while (this.phase < 1) {
        this.emit(this.prev + (this.cur - this.prev) * this.phase)
        this.phase += this.step
      }
      this.phase -= 1
      this.prev = this.cur
    }
    return true
  }
}

registerProcessor('pcm16-framer', PCM16Framer)
