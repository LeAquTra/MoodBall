import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../lib/api'
import type { ToolEvent } from '../lib/types'
import { useUiStore } from './ui'

export const useCameraStore = defineStore('camera', () => {
  const ui = useUiStore()
  const enabled = ref(true)
  const opencv = ref(true)
  const opened = ref(false)
  const width = ref(0)
  const height = ref(0)
  const lastError = ref('')
  const previewOn = ref(false)
  const previewKey = ref(Date.now())
  const loading = ref(false)
  const snapshotInfo = ref<Record<string, unknown> | null>(null)
  const images = ref<{ id: string; url: string; created_at: string }[]>([])

  const previewUrl = computed(() => `/api/camera/preview/?t=${previewKey.value}`)

  async function loadStatus() {
    try {
      const result = await api.cameraStatus()
      enabled.value = result.camera.enabled
      opencv.value = result.camera.opencv
      opened.value = result.camera.opened
      width.value = result.camera.width
      height.value = result.camera.height
      lastError.value = result.camera.last_error
    } catch (err) {
      lastError.value = (err as Error).message
    }
  }

  async function startPreview() {
    previewOn.value = true
    previewKey.value = Date.now()
    await loadStatus()
  }

  async function stopPreview() {
    previewOn.value = false
    try {
      await api.cameraRelease()
    } catch {
      /* ignore */
    }
    await loadStatus()
  }

  async function refresh() {
    previewKey.value = Date.now()
    await loadStatus()
  }

  async function snapshot(conversationId?: string): Promise<Record<string, unknown> | null> {
    loading.value = true
    try {
      const result = await api.snapshot(conversationId)
      snapshotInfo.value = result
      await loadImages(conversationId)
      ui.notify('已抓取一帧', 'success')
      return result
    } catch (err) {
      ui.notify((err as Error).message, 'error')
      return null
    } finally {
      loading.value = false
      void loadStatus()
    }
  }

  async function loadImages(conversationId?: string) {
    try {
      const result = await api.images(conversationId)
      images.value = result.items
    } catch {
      /* ignore */
    }
  }

  async function clearImages() {
    try {
      const result = await api.clearImages()
      images.value = []
      snapshotInfo.value = null
      ui.notify(`已清空 ${result.deleted} 张图片`, 'success')
    } catch (err) {
      ui.notify((err as Error).message, 'error')
    }
  }

  function snapshotAsToolEvent(): ToolEvent | null {
    if (!snapshotInfo.value) return null
    return {
      name: 'capture_photo',
      source: 'builtin',
      status: 'ok',
      duration_ms: 0,
      result_preview: String(snapshotInfo.value.url ?? ''),
    }
  }

  return {
    enabled,
    opencv,
    opened,
    width,
    height,
    lastError,
    previewOn,
    previewKey,
    previewUrl,
    loading,
    snapshotInfo,
    images,
    loadStatus,
    startPreview,
    stopPreview,
    refresh,
    snapshot,
    loadImages,
    clearImages,
    snapshotAsToolEvent,
  }
})
