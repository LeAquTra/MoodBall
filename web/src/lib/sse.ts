export interface SSEMessage {
  event: string
  data: Record<string, unknown>
}

export interface SSEOptions {
  signal?: AbortSignal
  onOpen?: () => void
  onEvent: (message: SSEMessage) => void
  onError?: (error: Error) => void
}

export async function streamSSE(url: string, payload: unknown, options: SSEOptions): Promise<void> {
  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: options.signal,
    })
  } catch (error) {
    if ((error as Error).name === 'AbortError') return
    options.onError?.(error as Error)
    throw error
  }

  if (!response.ok || !response.body) {
    let message = `请求失败（${response.status}）`
    try {
      const body = await response.json()
      message = body?.error?.message || message
    } catch {
      /* ignore */
    }
    const error = new Error(message)
    options.onError?.(error)
    throw error
  }

  options.onOpen?.()
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const blocks = buffer.split(/\r?\n\r?\n/)
      buffer = blocks.pop() || ''
      for (const block of blocks) {
        const parsed = parseBlock(block)
        if (parsed) options.onEvent(parsed)
      }
    }
    const tail = parseBlock(buffer)
    if (tail) options.onEvent(tail)
  } catch (error) {
    if ((error as Error).name !== 'AbortError') {
      options.onError?.(error as Error)
      throw error
    }
  }
}

function parseBlock(block: string): SSEMessage | null {
  if (!block.trim()) return null
  const lines = block.split(/\r?\n/)
  let event = 'message'
  const dataLines: string[] = []
  for (const line of lines) {
    if (line.startsWith(':')) continue
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!dataLines.length) return null
  const raw = dataLines.join('\n')
  try {
    const data = JSON.parse(raw) as Record<string, unknown>
    return { event, data }
  } catch {
    return { event, data: { raw } }
  }
}
