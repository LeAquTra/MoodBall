export type ThemeName = 'dark' | 'light'

export type VoiceState =
  | 'idle'
  | 'arming'
  | 'armed'
  | 'triggered'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'error'

export type InputMode = 'voice' | 'keyboard'

export type LogRole = 'user' | 'assistant' | 'system'

export type CommandEffect = 'stop-voice' | 'focus-input' | 'scroll-commands' | 'scroll-top'

export interface LogEntry {
  id: number
  role: LogRole
  text: string
  at: number
  commandId?: string
}
