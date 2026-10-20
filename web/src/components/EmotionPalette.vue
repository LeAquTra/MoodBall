<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import Icon from './Icon.vue'
import { useBallStore } from '../stores/ball'
import { useUiStore } from '../stores/ui'

const emit = defineEmits<{ (event: 'close'): void }>()
const ball = useBallStore()
const ui = useUiStore()
const search = ref('')
const group = ref('all')
const searchInput = ref<HTMLInputElement | null>(null)

const groupNames: Record<string, string> = {
  all: '全部',
  life: '生命周期',
  emotion: '情绪',
  agent: '状态',
  custom: '自定义',
}

const groupCounts = computed(() => {
  const counts: Record<string, number> = { all: ball.emotions.length }
  for (const emotion of ball.emotions) counts[emotion.group] = (counts[emotion.group] ?? 0) + 1
  return counts
})

const filtered = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return ball.emotions.filter((emotion) => {
    if (group.value !== 'all' && emotion.group !== group.value) return false
    if (!keyword) return true
    const haystack = `${emotion.id} ${emotion.name} ${emotion.desc ?? ''}`.toLowerCase()
    return haystack.includes(keyword)
  })
})

function choose(id: string) {
  ball.applyEmotion(id, 'interaction', true)
  ball.setTips(`切到 #${id} ${ball.emotions.find((item) => item.id === id)?.name ?? ''}`)
}

function close() {
  ui.paletteOpen = false
  emit('close')
}

onMounted(async () => {
  await nextTick()
  searchInput.value?.focus()
})
</script>

<template>
  <div class="drawer-layer" @click.self="close">
    <aside class="drawer drawer-palette" role="dialog" aria-modal="false" aria-label="表情库">
      <header class="drawer-head">
        <div class="drawer-title">
          <h2>表情库</h2>
          <span class="drawer-sub">{{ ball.emotions.length }} 种表情 · 点击立即切换</span>
        </div>
        <div class="drawer-actions">
          <button type="button" class="icon-btn" title="关闭" aria-label="关闭表情库" @click="close">
            <Icon name="close" />
          </button>
        </div>
      </header>

      <div class="memory-toolbar">
        <label class="search-field">
          <Icon name="search" :size="14" />
          <input ref="searchInput" v-model="search" type="search" placeholder="搜索 ID / 名称 / 描述" />
        </label>
      </div>

      <div class="tag-cloud">
        <button
          v-for="key in ['all', 'life', 'emotion', 'agent', 'custom']"
          :key="key"
          type="button"
          class="tag-btn"
          :class="{ on: group === key }"
          @click="group = key"
        >
          {{ groupNames[key] }}
          <span class="mono">{{ groupCounts[key] ?? 0 }}</span>
        </button>
      </div>

      <div class="drawer-body">
        <div class="emotion-grid">
          <button
            v-for="emotion in filtered"
            :key="emotion.id"
            type="button"
            class="emotion-card"
            :class="{ on: ball.current === emotion.id }"
            @click="choose(emotion.id)"
          >
            <span class="emotion-card-id mono">#{{ emotion.id }}</span>
            <span class="emotion-card-name">{{ emotion.name }}</span>
            <span class="emotion-card-desc">{{ emotion.desc || groupNames[emotion.group] || emotion.group }}</span>
          </button>
        </div>
        <div v-if="!filtered.length" class="memory-empty">没有匹配的表情。</div>
      </div>
    </aside>
  </div>
</template>
