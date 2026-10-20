import { reactive, ref, watch } from 'vue'
import type { LogEntry, LogRole, ThemeName } from './types'

const THEME_KEY = 'arouse.theme'
const TTS_KEY = 'arouse.tts'

function readTheme(): ThemeName {
  try {
    const query = new URLSearchParams(window.location.search).get('theme')
    if (query === 'light' || query === 'dark') return query
    return localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

function readTts(): boolean {
  try {
    return localStorage.getItem(TTS_KEY) !== 'off'
  } catch {
    return true
  }
}

export const theme = ref<ThemeName>(readTheme())

export const ttsEnabled = ref(readTts())

export const panels = reactive({
  settings: false,
})

export const logs = ref<LogEntry[]>([])

watch(
  theme,
  (value) => {
    document.documentElement.dataset.theme = value
    try {
      localStorage.setItem(THEME_KEY, value)
    } catch {
      /* 隐私模式下忽略 */
    }
  },
  { immediate: true },
)

watch(ttsEnabled, (value) => {
  try {
    localStorage.setItem(TTS_KEY, value ? 'on' : 'off')
  } catch {
    /* 忽略 */
  }
})

let logSeq = 0

export function pushLog(role: LogRole, text: string, commandId?: string) {
  const entry: LogEntry = { id: ++logSeq, role, text, at: Date.now(), commandId }
  logs.value = [...logs.value.slice(-39), entry]
}

export function clearLogs() {
  logs.value = []
  pushLog('system', '控制台已清空')
}

export function toggleTheme(): ThemeName {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  return theme.value
}

export interface ToastState {
  id: number
  message: string
}

export const toast = ref<ToastState | null>(null)

let toastSeq = 0
let toastTimer = 0

export function notify(message: string) {
  const id = ++toastSeq
  toast.value = { id, message }
  window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => {
    if (toast.value?.id === id) toast.value = null
  }, 2800)
}
