import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../lib/api'
import type { AppMeta, AppSettings, Health, Provider } from '../lib/types'
import { useUiStore } from './ui'

export const useSettingsStore = defineStore('settings', () => {
  const ui = useUiStore()
  const settings = ref<AppSettings | null>(null)
  const meta = ref<AppMeta | null>(null)
  const health = ref<Health | null>(null)
  const providers = ref<Provider[]>([])
  const revealKeys = ref(false)
  const loading = ref(false)
  const saving = ref(false)
  const lastHealthAt = ref(0)

  const providersByKind = computed(() => {
    const map: Record<string, Provider[]> = { chat: [], vision: [], tts: [], asr: [] }
    for (const provider of providers.value) {
      ;(map[provider.kind] ??= []).push(provider)
    }
    return map
  })

  async function loadSettings() {
    try {
      const result = await api.settings()
      settings.value = result.settings
    } catch (err) {
      ui.notify((err as Error).message, 'error')
    }
  }

  async function loadMeta() {
    try {
      meta.value = await api.meta()
    } catch {
      /* meta 失败不影响主流程 */
    }
  }

  async function loadHealth() {
    try {
      health.value = await api.health()
      lastHealthAt.value = Date.now()
    } catch {
      /* 健康检查失败静默 */
    }
  }

  async function loadProviders(forceReveal = false) {
    try {
      const result = await api.providers(forceReveal || revealKeys.value)
      providers.value = result.items
    } catch (err) {
      ui.notify((err as Error).message, 'error')
    }
  }

  async function loadAll() {
    loading.value = true
    await Promise.allSettled([loadSettings(), loadMeta(), loadHealth(), loadProviders()])
    loading.value = false
  }

  async function save(patch: Partial<AppSettings>) {
    saving.value = true
    try {
      const result = await api.saveSettings(patch)
      settings.value = result.settings
      ui.notify('设置已保存', 'success')
    } catch (err) {
      ui.notify((err as Error).message, 'error')
    } finally {
      saving.value = false
    }
  }

  async function createProvider(payload: Record<string, unknown>) {
    try {
      const result = await api.createProvider(payload)
      providers.value.push(result.provider)
      ui.notify('Provider 已添加', 'success')
      return result.provider
    } catch (err) {
      ui.notify((err as Error).message, 'error')
      return null
    }
  }

  async function updateProvider(id: string, payload: Record<string, unknown>) {
    try {
      const result = await api.updateProvider(id, payload)
      const index = providers.value.findIndex((item) => item.id === id)
      if (index >= 0) providers.value[index] = result.provider
      ui.notify('Provider 已更新', 'success')
      return result.provider
    } catch (err) {
      ui.notify((err as Error).message, 'error')
      return null
    }
  }

  async function deleteProvider(id: string) {
    try {
      await api.deleteProvider(id)
      providers.value = providers.value.filter((item) => item.id !== id)
      ui.notify('Provider 已删除', 'success')
    } catch (err) {
      ui.notify((err as Error).message, 'error')
    }
  }

  async function testProvider(id: string) {
    try {
      const result = await api.testProvider(id)
      const ok = result.ok && result.result?.ok
      ui.notify(
        ok
          ? `连接正常 · ${result.result?.latency_ms ?? 0} ms`
          : result.result?.message || '连接失败',
        ok ? 'success' : 'error',
      )
      return result.result
    } catch (err) {
      ui.notify((err as Error).message, 'error')
      return null
    }
  }

  async function revealAllKeys() {
    revealKeys.value = true
    await loadProviders(true)
  }

  return {
    settings,
    meta,
    health,
    providers,
    providersByKind,
    revealKeys,
    loading,
    saving,
    lastHealthAt,
    loadSettings,
    loadMeta,
    loadHealth,
    loadProviders,
    loadAll,
    save,
    createProvider,
    updateProvider,
    deleteProvider,
    testProvider,
    revealAllKeys,
  }
})
