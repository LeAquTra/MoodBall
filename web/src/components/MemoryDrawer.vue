<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Icon from './Icon.vue'
import { useMemoryStore } from '../stores/memory'
import { useUiStore } from '../stores/ui'
import { formatDay } from '../lib/format'
import type { MemoryItem } from '../lib/types'

const memory = useMemoryStore()
const ui = useUiStore()

onMounted(() => {
  void memory.load()
})

const editingId = ref<string | null>(null)
const fact = ref('')
const tags = ref('')
const pinned = ref(false)

const editing = computed(() => editingId.value !== null)
const editorTitle = computed(() => (editingId.value === 'new' ? '新增记忆' : '编辑记忆'))
const statsLine = computed(
  () => `${memory.stats.total} 条 · ${memory.stats.pinned} 条置顶 · 7 天内用过 ${memory.stats.used_7d} 条`,
)

function tagsOf(item: MemoryItem): string[] {
  if (item.tag_list?.length) return item.tag_list
  return item.tags
    .split(/[,，]/)
    .map((tag) => tag.trim())
    .filter(Boolean)
}

function startCreate() {
  editingId.value = 'new'
  fact.value = ''
  tags.value = ''
  pinned.value = false
}

function startEdit(item: MemoryItem) {
  editingId.value = item.id
  fact.value = item.fact
  tags.value = tagsOf(item).join(', ')
  pinned.value = item.pinned
}

function cancel() {
  editingId.value = null
  fact.value = ''
  tags.value = ''
  pinned.value = false
}

async function save() {
  const content = fact.value.trim()
  if (!content) return
  const target = editingId.value
  const ok =
    target === 'new'
      ? await memory.create(content, tags.value, pinned.value)
      : target
        ? await memory.update(target, { fact: content, tags: tags.value, pinned: pinned.value })
        : false
  if (!ok) return
  cancel()
  if (target && target !== 'new') await memory.load({ silent: true })
}

async function remove(item: MemoryItem) {
  if (!window.confirm(`删除这条记忆？\n\n${item.fact}`)) return
  await memory.remove(item.id)
}

async function clearAll() {
  if (!window.confirm('清空所有未置顶的记忆？置顶记忆会保留。')) return
  await memory.clearAll(true)
}

function openMemorySettings() {
  ui.memoryOpen = false
  ui.openSettings('memory')
}

function selectTag(tag: string) {
  memory.selectTag(tag)
}

function close() {
  ui.memoryOpen = false
}
</script>

<template>
  <div class="drawer-layer" @click.self="close">
    <aside class="drawer drawer-memory" role="dialog" aria-modal="false" aria-label="长期记忆">
      <header class="drawer-head">
        <div class="drawer-title">
          <h2>记忆</h2>
          <span class="drawer-sub">{{ statsLine }}</span>
        </div>
        <div class="drawer-actions">
          <button type="button" class="icon-btn" title="新增记忆" aria-label="新增记忆" @click="startCreate">
            <Icon name="plus" />
          </button>
          <button type="button" class="icon-btn" title="关闭" aria-label="关闭记忆" @click="close">
            <Icon name="close" />
          </button>
        </div>
      </header>

      <div class="memory-toolbar">
        <label class="search-field">
          <Icon name="search" :size="14" />
          <input
            v-model="memory.query"
            type="search"
            placeholder="搜索事实或标签"
            aria-label="搜索记忆"
            @input="memory.scheduleSearch()"
          />
        </label>
        <select v-model="memory.sort" class="sort-select" aria-label="排序" @change="memory.setSort(memory.sort)">
          <option value="recent">最近</option>
          <option value="pinned">置顶优先</option>
          <option value="used">常用</option>
          <option value="oldest">最早</option>
        </select>
      </div>

      <div v-if="memory.tags.length" class="tag-cloud">
        <button
          type="button"
          class="tag-btn"
          :class="{ on: !memory.tag }"
          @click="selectTag(memory.tag)"
        >
          全部
          <span class="mono">{{ memory.stats.total }}</span>
        </button>
        <button
          v-for="item in memory.tags"
          :key="item.tag"
          type="button"
          class="tag-btn"
          :class="{ on: memory.tag === item.tag }"
          @click="selectTag(item.tag)"
        >
          #{{ item.tag }}
          <span class="mono">{{ item.count }}</span>
        </button>
      </div>

      <div v-if="memory.recalled.length" class="recall-note">
        <Icon name="spark" :size="13" />
        上一轮小球回想了 {{ memory.recalled.length }} 条记忆
      </div>

      <div class="drawer-body">
        <form v-if="editing" class="memory-editor" @submit.prevent="save">
          <div class="editor-head">
            <strong>{{ editorTitle }}</strong>
            <span class="mono">{{ fact.length }}/500</span>
          </div>
          <label class="field">
            <span>事实（一句话）</span>
            <textarea
              v-model="fact"
              rows="3"
              maxlength="500"
              placeholder="例如：我每天早上喝一杯冰美式。"
              autofocus
            ></textarea>
          </label>
          <label class="field">
            <span>标签（逗号分隔）</span>
            <input v-model="tags" maxlength="300" placeholder="偏好, 咖啡, 早晨" />
          </label>
          <label class="check-row">
            <input v-model="pinned" type="checkbox" />
            置顶：之后每轮对话都会带上这条记忆
          </label>
          <div class="editor-actions">
            <button type="button" class="ghost-btn" @click="cancel">取消</button>
            <button type="submit" class="paper-btn" :disabled="memory.saving || !fact.trim()">
              {{ memory.saving ? '保存中…' : '保存' }}
            </button>
          </div>
        </form>

        <template v-else>
          <div v-if="memory.loading && !memory.items.length" class="memory-empty">正在读取记忆…</div>

          <article
            v-for="item in memory.items"
            :key="item.id"
            class="memory-card"
            :class="{ pinned: item.pinned }"
          >
            <div class="memory-card-top">
              <span class="source-badge" :class="item.source">{{ memory.sourceLabel(item.source) }}</span>
              <span v-if="item.pinned" class="pin-badge">
                <Icon name="pin" :size="11" />
                置顶
              </span>
              <span class="memory-time mono">{{ formatDay(item.updated_at || item.created_at) }}</span>
              <div class="memory-actions">
                <button
                  type="button"
                  class="icon-btn xs"
                  :class="{ on: item.pinned }"
                  :title="item.pinned ? '取消置顶' : '置顶'"
                  :aria-label="item.pinned ? '取消置顶' : '置顶'"
                  @click="memory.togglePin(item)"
                >
                  <Icon name="pin" :size="13" />
                </button>
                <button type="button" class="icon-btn xs" title="编辑" aria-label="编辑记忆" @click="startEdit(item)">
                  <Icon name="edit" :size="13" />
                </button>
                <button
                  type="button"
                  class="icon-btn xs danger"
                  title="删除"
                  aria-label="删除记忆"
                  @click="remove(item)"
                >
                  <Icon name="trash" :size="13" />
                </button>
              </div>
            </div>
            <p class="memory-fact">{{ item.fact }}</p>
            <div class="memory-foot">
              <span v-for="tag in tagsOf(item)" :key="tag" class="tag">#{{ tag }}</span>
              <span class="memory-used">{{ item.use_count ? `用过 ${item.use_count} 次` : '未用过' }}</span>
            </div>
          </article>

          <div v-if="memory.isEmpty" class="memory-empty">
            <template v-if="memory.activeFilters">没有匹配的记忆。</template>
            <template v-else>
              还没有长期记忆。对小球说「记住：……」，或点右上角 + 手动添加；置顶的记忆每轮都会带上。
            </template>
          </div>
          <div v-if="memory.error" class="inline-error">
            <span>{{ memory.error }}</span>
            <button type="button" class="ghost-btn tiny-btn" @click="memory.load()">重试</button>
          </div>
        </template>
      </div>

      <footer class="drawer-foot">
        <span class="foot-note">
          自动提取<strong :class="{ on: memory.autoExtraction }">{{ memory.autoExtraction ? '已开启' : '已关闭' }}</strong>
        </span>
        <button type="button" class="link-btn" @click="openMemorySettings">记忆设置</button>
        <button type="button" class="link-btn" @click="memory.load()">刷新</button>
        <button type="button" class="link-btn danger" @click="clearAll">清空</button>
      </footer>
    </aside>
  </div>
</template>
