export interface ApiErrorPayload {
  code: string
  message: string
  retryable?: boolean
  request_id?: string
}

export class ApiError extends Error {
  code: string
  retryable: boolean
  requestId?: string
  status: number

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.message || `HTTP ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.code = payload.code || 'HTTP_ERROR'
    this.retryable = Boolean(payload.retryable)
    this.requestId = payload.request_id
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let payload: ApiErrorPayload = {
    code: `HTTP_${response.status}`,
    message: `请求失败（${response.status}）`,
  }
  try {
    const body = await response.json()
    if (body?.error) payload = body.error
  } catch {
    /* ignore */
  }
  return new ApiError(response.status, payload)
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })
  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  health: () => request<import('./types').Health>('/api/health/'),
  meta: () => request<{ ok: boolean } & import('./types').AppMeta>('/api/meta/'),
  emotions: () => request<{ ok: boolean; items: import('./types').Emotion[]; count: number }>('/api/emotions/'),

  settings: () => request<{ ok: boolean; settings: import('./types').AppSettings }>('/api/settings/'),
  saveSettings: (patch: Partial<import('./types').AppSettings>) =>
    request<{ ok: boolean; settings: import('./types').AppSettings }>('/api/settings/', {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),

  conversations: () => request<{ ok: boolean; items: import('./types').Conversation[] }>('/api/conversations/'),
  createConversation: (title = '') =>
    request<{ ok: boolean; conversation: import('./types').Conversation }>('/api/conversations/', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
  conversation: (id: string) =>
    request<{ ok: boolean; conversation: import('./types').Conversation & { messages: import('./types').Message[] } }>(
      `/api/conversations/${id}/`,
    ),
  deleteConversation: (id: string) =>
    request<{ ok: boolean }>(`/api/conversations/${id}/`, { method: 'DELETE' }),
  messages: (id: string, limit = 200) =>
    request<{ ok: boolean; items: import('./types').Message[]; total: number }>(
      `/api/conversations/${id}/messages/?limit=${limit}`,
    ),
  events: (id: string) =>
    request<{ ok: boolean; emotions: unknown[]; runs: unknown[] }>(`/api/conversations/${id}/events/`),

  memories: (params: { q?: string; tag?: string; sort?: string; limit?: number; offset?: number } = {}) => {
    const search = new URLSearchParams()
    if (params.q) search.set('q', params.q)
    if (params.tag) search.set('tag', params.tag)
    if (params.sort) search.set('sort', params.sort)
    if (params.limit) search.set('limit', String(params.limit))
    if (params.offset) search.set('offset', String(params.offset))
    const suffix = search.toString()
    return request<import('./types').MemoryListResponse>(`/api/memories/${suffix ? `?${suffix}` : ''}`)
  },
  createMemory: (payload: { fact: string; tags?: string; pinned?: boolean; source?: string }) =>
    request<{ ok: boolean; memory: import('./types').MemoryItem; created: boolean }>('/api/memories/', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateMemory: (
    id: string,
    payload: Partial<{ fact: string; tags: string; pinned: boolean; confidence: number }>,
  ) =>
    request<{ ok: boolean; memory: import('./types').MemoryItem }>(`/api/memories/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteMemory: (id: string) => request<{ ok: boolean }>(`/api/memories/${id}/`, { method: 'DELETE' }),
  bulkDeleteMemories: (ids: string[]) =>
    request<{ ok: boolean; deleted: number }>('/api/memories/bulk-delete/', {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }),
  clearMemories: (keepPinned = true) =>
    request<{ ok: boolean; deleted: number }>('/api/memories/clear/', {
      method: 'POST',
      body: JSON.stringify({ keep_pinned: keepPinned }),
    }),

  providers: (reveal = false) =>
    request<{ ok: boolean; items: import('./types').Provider[]; kinds: string[] }>(
      `/api/providers/${reveal ? '?reveal=1' : ''}`,
    ),
  createProvider: (payload: Record<string, unknown>) =>
    request<{ ok: boolean; provider: import('./types').Provider }>('/api/providers/', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateProvider: (id: string, payload: Record<string, unknown>) =>
    request<{ ok: boolean; provider: import('./types').Provider }>(`/api/providers/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteProvider: (id: string) => request<{ ok: boolean }>(`/api/providers/${id}/`, { method: 'DELETE' }),
  testProvider: (id: string) =>
    request<{ ok: boolean; result: { ok: boolean; message?: string; latency_ms?: number; code?: string } }>(
      `/api/providers/${id}/test/`,
      { method: 'POST' },
    ),

  mcpServers: () =>
    request<{ ok: boolean; items: import('./types').McpServer[] }>('/api/mcp/servers/'),
  createMcpServer: (payload: Record<string, unknown>) =>
    request<{ ok: boolean; server: import('./types').McpServer }>('/api/mcp/servers/', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateMcpServer: (id: string, payload: Record<string, unknown>) =>
    request<{ ok: boolean; server: import('./types').McpServer }>(`/api/mcp/servers/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteMcpServer: (id: string) =>
    request<{ ok: boolean }>(`/api/mcp/servers/${id}/`, { method: 'DELETE' }),
  testMcpServer: (id: string) =>
    request<{ ok: boolean; tools: unknown[]; tool_count: number; latency_ms: number }>(
      `/api/mcp/servers/${id}/test/`,
      { method: 'POST' },
    ),
  refreshMcpServer: (id: string) =>
    request<{ ok: boolean; tools: unknown[]; tool_count: number; registry_size: number }>(
      `/api/mcp/servers/${id}/refresh/`,
      { method: 'POST' },
    ),
  importMcp: (payload: Record<string, unknown>) =>
    request<{ ok: boolean; imported: number }>('/api/mcp/import/', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  exportMcp: () => request<{ ok: boolean; config: Record<string, unknown> }>('/api/mcp/export/'),

  tools: () =>
    request<{ ok: boolean; items: import('./types').ToolEntry[]; last_error: string }>('/api/tools/'),
  refreshTools: () =>
    request<{ ok: boolean; items: import('./types').ToolEntry[]; last_error: string }>('/api/tools/refresh/', {
      method: 'POST',
    }),
  toggleTool: (name: string, enabled: boolean) =>
    request<{ ok: boolean }>(`/api/tools/${encodeURIComponent(name)}/toggle/`, {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    }),
  invokeTool: (name: string, args: Record<string, unknown>) =>
    request<{
      ok: boolean
      name: string
      status: string
      duration_ms: number
      result: unknown
      error?: string | null
    }>(`/api/tools/${encodeURIComponent(name)}/invoke/`, {
      method: 'POST',
      body: JSON.stringify({ args }),
    }),

  cameraStatus: () =>
    request<{ ok: boolean; camera: { enabled: boolean; opencv: boolean; opened: boolean; width: number; height: number; last_error: string } }>(
      '/api/camera/status/',
    ),
  cameraRelease: () => request<{ ok: boolean }>('/api/camera/release/', { method: 'POST' }),
  snapshot: (conversationId?: string) =>
    request<Record<string, unknown>>('/api/camera/snapshot/', {
      method: 'POST',
      body: JSON.stringify({ conversation_id: conversationId }),
    }),
  images: (conversationId?: string) =>
    request<{ ok: boolean; items: { id: string; url: string; created_at: string }[] }>(
      `/api/images/${conversationId ? `?conversation_id=${conversationId}` : ''}`,
    ),
  clearImages: () => request<{ ok: boolean; deleted: number }>('/api/images/', { method: 'DELETE' }),

  ttsPreview: (text: string, voice?: string) =>
    request<{ ok: boolean; audio_url: string; duration_ms: number; latency_ms: number }>('/api/tts/preview/', {
      method: 'POST',
      body: JSON.stringify({ text, voice }),
    }),
  voiceStatus: () =>
    request<{ ok: boolean; asr: { ok: boolean; message?: string }; enabled: boolean; wake_word: string }>(
      '/api/voice/status/',
    ),

  providerSeed: () => request<{ ok: boolean; count: number }>('/api/providers/seed/', { method: 'POST' }),
}
