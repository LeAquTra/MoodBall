import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ToastKind = 'info' | 'success' | 'warning' | 'error'
export type SettingsTab = 'providers' | 'mcp' | 'tools' | 'voice' | 'memory' | 'privacy'

export interface Toast {
  id: number
  message: string
  kind: ToastKind
}

let nextToastId = 1

export const useUiStore = defineStore('ui', () => {
  const toasts = ref<Toast[]>([])
  const settingsOpen = ref(false)
  const settingsTab = ref<SettingsTab>('providers')
  const cameraOpen = ref(false)
  const paletteOpen = ref(false)
  const transcriptOpen = ref(false)
  const memoryOpen = ref(false)
  const reducedMotion = ref(false)

  function notify(message: string, kind: ToastKind = 'info', ms = 4200) {
    if (!message) return
    const id = nextToastId++
    toasts.value.push({ id, message, kind })
    window.setTimeout(() => dismiss(id), ms)
  }

  function dismiss(id: number) {
    toasts.value = toasts.value.filter((toast) => toast.id !== id)
  }

  function openSettings(tab: SettingsTab = 'providers') {
    settingsTab.value = tab
    settingsOpen.value = true
  }

  function closeSettings() {
    settingsOpen.value = false
  }

  function toggleCamera() {
    cameraOpen.value = !cameraOpen.value
  }

  function toggleTranscript() {
    transcriptOpen.value = !transcriptOpen.value
  }

  function toggleMemory() {
    memoryOpen.value = !memoryOpen.value
  }

  /** Esc 的关闭顺序：设置 → 表情库 → 摄像头 → 记忆 → 对话记录。 */
  function closeTopLayer(): boolean {
    if (settingsOpen.value) {
      settingsOpen.value = false
      return true
    }
    if (paletteOpen.value) {
      paletteOpen.value = false
      return true
    }
    if (cameraOpen.value) {
      cameraOpen.value = false
      return true
    }
    if (memoryOpen.value) {
      memoryOpen.value = false
      return true
    }
    if (transcriptOpen.value) {
      transcriptOpen.value = false
      return true
    }
    return false
  }

  return {
    toasts,
    settingsOpen,
    settingsTab,
    cameraOpen,
    paletteOpen,
    transcriptOpen,
    memoryOpen,
    reducedMotion,
    notify,
    dismiss,
    openSettings,
    closeSettings,
    toggleCamera,
    toggleTranscript,
    toggleMemory,
    closeTopLayer,
  }
})
