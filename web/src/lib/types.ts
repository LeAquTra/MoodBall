export type EmotionGroup = 'life' | 'emotion' | 'agent' | 'custom'

export interface Emotion {
  id: string
  name: string
  group: EmotionGroup | string
  desc?: string
  en?: { name?: string; desc?: string }
}

export interface Conversation {
  id: string
  title: string
  status: string
  summary?: string
  created_at: string
  updated_at: string
  message_count?: number
}

export interface ToolEvent {
  name: string
  source: string
  server?: string | null
  status: 'ok' | 'error' | 'timeout'
  duration_ms: number
  args?: Record<string, unknown>
  result_preview?: string
  result?: unknown
}

export type MemorySource = 'manual' | 'agent' | 'auto'

export interface MemoryItem {
  id: string
  conversation_id?: string | null
  fact: string
  tags: string
  tag_list?: string[]
  confidence: number
  source: MemorySource
  pinned: boolean
  use_count: number
  last_used_at?: string | null
  created_at: string
  updated_at: string
}

export interface MemoryTag {
  tag: string
  count: number
}

export interface MemoryStats {
  total: number
  pinned: number
  manual: number
  agent: number
  auto: number
  used: number
  used_7d: number
}

export interface MemorySettings {
  enabled: boolean
  auto_extract: boolean
  max_items: number
  recall_limit: number
  pinned_limit: number
}

export interface MemoryListResponse {
  ok: boolean
  items: MemoryItem[]
  total: number
  limit: number
  offset: number
  tags: MemoryTag[]
  stats: MemoryStats
  settings: MemorySettings
}

export interface Message {
  id: string
  client_id?: string
  conversation_id?: string
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: string
  emotion_id?: string
  tokens_in?: number
  tokens_out?: number
  latency_ms?: number
  created_at: string
  meta?: { tool_events?: ToolEvent[]; [key: string]: unknown }
  pending?: boolean
  tool_events?: ToolEvent[]
}

export interface AppSettings {
  wake_word: string
  wake_variants: string[]
  wake_confirm_hits: number
  wake_cooldown_ms: number
  command_timeout_ms: number
  tts_voice: string
  tts_model: string
  tts_enabled: boolean
  camera_index: number
  camera_backend: string
  camera_width: number
  camera_height: number
  retain_images: boolean
  image_retention_days: number
  audio_retention_days: number
  speak_replies: boolean
  emotion_style: string
  reduced_motion: boolean
  agent_enabled: boolean
  mcp_enabled: boolean
  memory_enabled: boolean
  memory_auto_extract: boolean
  memory_max_items: number
}

export interface Provider {
  id: string
  kind: 'chat' | 'vision' | 'tts' | 'asr'
  name: string
  base_url: string
  model: string
  api_key: string
  api_key_set: boolean
  extra: Record<string, unknown>
  enabled: boolean
  is_default: boolean
  created_at: string
  updated_at: string
}

export interface McpTool {
  id: string
  server: string
  name: string
  description: string
  input_schema: Record<string, unknown>
  enabled: boolean
  last_seen_at: string
}

export interface McpServer {
  id: string
  name: string
  transport: 'stdio' | 'http' | 'sse' | 'streamable_http'
  command: string
  args: string[]
  env: Record<string, string>
  url: string
  headers: Record<string, string>
  tool_prefix: string
  enabled: boolean
  auto_start: boolean
  timeout_s: number
  last_error: string
  last_seen_at?: string | null
  tool_count?: number
  tools?: McpTool[]
  created_at: string
  updated_at: string
}

export interface ToolEntry {
  name: string
  source: 'builtin' | 'plugin' | 'mcp'
  server?: string | null
  description: string
  input_schema: Record<string, unknown>
  enabled: boolean
  tags: string[]
}

export interface Health {
  ok: boolean
  debug: boolean
  mode: string
  db: { ok: boolean; path?: string; error?: string }
  asr: { ok: boolean; message?: string; model?: string; cuda?: boolean; loaded?: boolean }
  camera: { ok: boolean; opened?: boolean; opencv?: boolean; message?: string }
  providers: Record<string, { configured: boolean; source: string; model: string; base_url: string }>
  mcp: { ok: boolean; total: number; enabled: number }
}

export interface AppMeta {
  app: string
  version: string
  wake_word: string
  wake_variants: string[]
  wake_confirm_hits: number
  asr_enabled: boolean
  tts_enabled: boolean
  camera_enabled: boolean
  agent_enabled: boolean
  mcp_enabled: boolean
  emotion_count: number
  time_zone: string
}

export interface ChatHandlers {
  onMeta?: (data: Record<string, unknown>) => void
  onState?: (data: { state: string; node?: string; emotion?: string }) => void
  onToken?: (text: string) => void
  onEmotion?: (data: { emotionId: string; intensity?: number; tips?: string; source?: string }) => void
  onTool?: (tool: ToolEvent) => void
  onMemory?: (data: { items: MemoryItem[]; count: number; query?: string }) => void
  onAudio?: (url: string, durationMs?: number) => void
  onWarning?: (message: string) => void
  onError?: (error: { code: string; message: string }) => void
  onDone?: (data: Record<string, unknown>) => void
}

export interface VoicePhase {
  state: 'idle' | 'arming' | 'armed' | 'triggered' | 'listening' | 'thinking' | 'acting' | 'speaking' | 'error'
}
