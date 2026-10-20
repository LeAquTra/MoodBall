export interface VoiceEvent {
  type: string
  [key: string]: unknown
}

export interface VoiceSocketHandlers {
  onEvent: (event: VoiceEvent) => void
  onOpen?: () => void
  onClose?: (clean: boolean) => void
  onError?: (message: string) => void
}

export class VoiceSocket {
  private ws?: WebSocket
  private retry = 0
  private closedByUser = false
  private connectPromise?: Promise<void>
  private startPayload: Record<string, unknown> = {}
  private reconnectTimer = 0

  constructor(private handlers: VoiceSocketHandlers) {}

  connect(payload: { conversation_id?: string | null; wake_word?: string; mode?: string }): Promise<void> {
    this.closedByUser = false
    this.startPayload = payload
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return Promise.resolve()
    if (this.connectPromise) return this.connectPromise

    this.connectPromise = new Promise((resolve, reject) => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const socket = new WebSocket(`${proto}://${location.host}/ws/voice/`)
      this.ws = socket
      socket.binaryType = 'arraybuffer'
      let settled = false

      socket.onopen = () => {
        this.retry = 0
        settled = true
        socket.send(JSON.stringify({ type: 'start', ...this.startPayload, mode: 'continuous' }))
        this.handlers.onOpen?.()
        resolve()
      }
      socket.onmessage = (event) => {
        if (typeof event.data !== 'string') return
        try {
          this.handlers.onEvent(JSON.parse(event.data) as VoiceEvent)
        } catch {
          /* ignore malformed */
        }
      }
      socket.onerror = () => {
        if (!settled) {
          settled = true
          reject(new Error('语音 WebSocket 连接失败'))
        }
      }
      socket.onclose = () => {
        this.ws = undefined
        this.connectPromise = undefined
        this.handlers.onClose?.(this.closedByUser)
        if (this.closedByUser) return
        if (!settled) {
          settled = true
          reject(new Error('语音 WebSocket 连接被关闭'))
        }
        const delay = Math.min(500 * 2 ** this.retry, 4000)
        this.retry += 1
        window.clearTimeout(this.reconnectTimer)
        this.reconnectTimer = window.setTimeout(() => {
          if (this.closedByUser) return
          this.connect(this.startPayload).catch(() => {
            /* onclose 会再次调度 */
          })
        }, delay)
      }
    })
    return this.connectPromise
  }

  sendPcm(buffer: ArrayBuffer): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return
    if (this.ws.bufferedAmount > 256 * 1024) return
    this.ws.send(buffer)
  }

  send(payload: Record<string, unknown>): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return
    this.ws.send(JSON.stringify(payload))
  }

  mute(value: boolean): void {
    this.send({ type: 'mute', value })
  }

  pttStart(): void {
    this.send({ type: 'ptt_start' })
  }

  pttStop(): void {
    this.send({ type: 'ptt_stop' })
  }

  ping(): void {
    this.send({ type: 'ping' })
  }

  stop(): void {
    this.closedByUser = true
    window.clearTimeout(this.reconnectTimer)
    this.reconnectTimer = 0
    this.connectPromise = undefined
    if (this.ws) {
      try {
        this.ws.send(JSON.stringify({ type: 'stop' }))
      } catch {
        /* ignore */
      }
      this.ws.close()
      this.ws = undefined
    }
    this.handlers.onClose?.(true)
  }

  isOpen(): boolean {
    return Boolean(this.ws && this.ws.readyState === WebSocket.OPEN)
  }
}
