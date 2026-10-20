import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../lib/api'
import type { MemoryItem, MemorySettings, MemorySource, MemoryStats, MemoryTag } from '../lib/types'
import { useUiStore } from './ui'

export type MemorySort = 'recent' | 'oldest' | 'used' | 'pinned'

const EMPTY_STATS: MemoryStats = {
  total: 0,
  pinned: 0,
  manual: 0,
  agent: 0,
  auto: 0,
  used: 0,
  used_7d: 0,
}

const EMPTY_SETTINGS: MemorySettings = {
  enabled: true,
  auto_extract: false,
  max_items: 500,
  recall_limit: 5,
  pinned_limit: 5,
}

const SOURCE_LABELS: Record<MemorySource, string> = {
  manual: '手动',
  agent: '对话',
  auto: '自动',
}

export const useMemoryStore = defineStore('memory', () => {
  const ui = useUiStore()

  const items = ref<MemoryItem[]>([])
  const tags = ref<MemoryTag[]>([])
  const stats = ref<MemoryStats>({ ...EMPTY_STATS })
  const settings = ref<MemorySettings>({ ...EMPTY_SETTINGS })
  const recalled = ref<MemoryItem[]>([])
  const query = ref('')
  const tag = ref('')
  const sort = ref<MemorySort>('recent')
  const loading = ref(false)
  const saving = ref(false)
  const loaded = ref(false)
  const error = ref('')

  let searchTimer = 0

  const activeFilters = computed(() => Boolean(query.value.trim() || tag.value))
  const isEmpty = computed(() => loaded.value && !loading.value && items.value.length === 0)
  const autoExtraction = computed(() => settings.value.enabled && settings.value.auto_extract)

  function sourceLabel(source: MemorySource | string): string {
    return SOURCE_LABELS[source as MemorySource] ?? String(source)
  }

  function mergeRecalled(item: MemoryItem) {
    const existing = items.value.find((row) => row.id === item.id)
    if (!existing) return
    existing.use_count = item.use_count
    existing.last_used_at = item.last_used_at
  }

  async function load(options: { silent?: boolean } = {}) {
    if (!options.silent) loading.value = true
    error.value = ''
    try {
      const result = await api.memories({
        q: query.value.trim() || undefined,
        tag: tag.value || undefined,
        sort: sort.value,
        limit: 200,
      })
      items.value = result.items
      tags.value = result.tags ?? []
      stats.value = result.stats ?? { ...EMPTY_STATS }
      settings.value = result.settings ?? { ...EMPTY_SETTINGS }
      loaded.value = true
    } catch (err) {
      error.value = (err as Error).message
      if (!options.silent) ui.notify(error.value, 'error')
    } finally {
      loading.value = false
    }
  }

  function scheduleSearch() {
    if (searchTimer) window.clearTimeout(searchTimer)
    searchTimer = window.setTimeout(() => void load({ silent: true }), 240)
  }

  function selectTag(next: string) {
    tag.value = tag.value === next ? '' : next
    void load({ silent: true })
  }

  function setSort(next: MemorySort) {
    sort.value = next
    void load({ silent: true })
  }

  async function create(fact: string, tagsText = '', isPinned = false): Promise<boolean> {
    const content = fact.trim()
    if (!content) return false
    saving.value = true
    try {
      const result = await api.createMemory({ fact: content, tags: tagsText, pinned: isPinned })
      ui.notify(result.created ? '记忆已保存' : '已有相似记忆，已合并标签', 'success')
      await load({ silent: true })
      return true
    } catch (err) {
      ui.notify((err as Error).message, 'error')
      return false
    } finally {
      saving.value = false
    }
  }

  async function update(
    id: string,
    payload: Partial<{ fact: string; tags: string; pinned: boolean }>,
  ): Promise<boolean> {
    saving.value = true
    try {
      const result = await api.updateMemory(id, payload)
      const index = items.value.findIndex((item) => item.id === id)
      if (index >= 0) items.value[index] = result.memory
      stats.value = {
        ...stats.value,
        pinned: items.value.filter((item) => item.pinned).length,
      }
      return true
    } catch (err) {
      ui.notify((err as Error).message, 'error')
      return false
    } finally {
      saving.value = false
    }
  }

  async function togglePin(item: MemoryItem) {
    const next = !item.pinned
    const ok = await update(item.id, { pinned: next })
    if (!ok) return
    ui.notify(next ? '已置顶，之后每轮都会带上它' : '已取消置顶', next ? 'success' : 'info')
    await load({ silent: true })
  }

  async function remove(id: string) {
    try {
      await api.deleteMemory(id)
      items.value = items.value.filter((item) => item.id !== id)
      recalled.value = recalled.value.filter((item) => item.id !== id)
      ui.notify('记忆已删除', 'success')
      await load({ silent: true })
    } catch (err) {
      ui.notify((err as Error).message, 'error')
    }
  }

  async function clearAll(keepPinned = true) {
    try {
      const result = await api.clearMemories(keepPinned)
      ui.notify(result.deleted ? `已清空 ${result.deleted} 条记忆` : '没有可清空的记忆', 'success')
      await load({ silent: true })
    } catch (err) {
      ui.notify((err as Error).message, 'error')
    }
  }

  /** 由 SSE `memory` 事件调用：记录上一轮召回，并同步本地使用次数。 */
  function noteRecalled(list: MemoryItem[]) {
    recalled.value = Array.isArray(list) ? list : []
    for (const item of recalled.value) mergeRecalled(item)
  }

  return {
    items,
    tags,
    stats,
    settings,
    recalled,
    query,
    tag,
    sort,
    loading,
    saving,
    loaded,
    error,
    activeFilters,
    isEmpty,
    autoExtraction,
    sourceLabel,
    load,
    scheduleSearch,
    selectTag,
    setSort,
    create,
    update,
    togglePin,
    remove,
    clearAll,
    noteRecalled,
  }
})
