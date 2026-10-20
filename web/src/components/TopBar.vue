<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import Icon from './Icon.vue'
import { useChatStore } from '../stores/chat'
import { useMemoryStore } from '../stores/memory'
import { useSettingsStore } from '../stores/settings'
import { useUiStore } from '../stores/ui'
import { useVoiceStore } from '../stores/voice'
import { formatDay } from '../lib/format'

const chat = useChatStore()
const memory = useMemoryStore()
const settings = useSettingsStore()
const ui = useUiStore()
const voice = useVoiceStore()

const showList = ref(false)
const menuRoot = ref<HTMLElement | null>(null)

const title = computed(() => chat.currentConversation?.title || '新对话')
const chatProvider = computed(() => settings.health?.providers?.chat)
const providerLabel = computed(() => {
  if (!chatProvider.value) return '检测中'
  return chatProvider.value.configured ? chatProvider.value.model || '已配置' : '未配置'
})
const providerLevel = computed(() => (chatProvider.value?.configured ? 'ok' : 'warn'))

const voiceLabel = computed(() => {
  if (!voice.active) return '语音待机'
  if (voice.state === 'error') return '语音异常'
  if (voice.listening) return '聆听中'
  if (voice.busy) return voice.statusText
  return '已就绪'
})
const voiceLevel = computed(() => {
  if (voice.state === 'error') return 'bad'
  if (voice.listening) return 'live'
  return voice.active ? 'ok' : 'idle'
})

const memoryCount = computed(() => memory.stats.total)
const messageCount = computed(() => chat.messages.length)

function toggleList() {
  showList.value = !showList.value
}

async function selectConversation(id: string) {
  showList.value = false
  await chat.selectConversation(id)
}

async function newConversation() {
  showList.value = false
  await chat.newConversation()
}

async function removeConversation(event: MouseEvent, id: string) {
  event.stopPropagation()
  await chat.deleteConversation(id)
}

function onDocumentClick(event: MouseEvent) {
  if (!showList.value) return
  const root = menuRoot.value
  if (root && !root.contains(event.target as Node)) showList.value = false
}

onMounted(() => document.addEventListener('click', onDocumentClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick))
</script>

<template>
  <header class="topbar">
    <div class="brand">
      <svg class="brand-mark" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="9.5" fill="#f3f0ea" />
        <circle cx="9" cy="11" r="1.35" fill="#08090a" />
        <circle cx="15" cy="11" r="1.35" fill="#08090a" />
        <path d="M9 15.2c1.9 1.6 3.9 1.6 6 0" fill="none" stroke="#08090a" stroke-width="1.4" stroke-linecap="round" />
      </svg>
      <span class="brand-name">MoodBall</span>
      <span class="brand-sub">local companion</span>
    </div>

    <div ref="menuRoot" class="conversation-menu">
      <button
        type="button"
        class="nav-btn"
        :aria-expanded="showList"
        title="切换对话"
        @click="toggleList"
      >
        <Icon name="chat" :size="14" />
        <span class="nav-btn-label">{{ title }}</span>
        <span class="nav-btn-count mono">{{ messageCount }}</span>
        <Icon name="chevron-down" :size="13" class="nav-chevron" />
      </button>
      <div v-if="showList" class="conversation-popover">
        <button type="button" class="conversation-item new" @click="newConversation">
          <Icon name="plus" :size="14" />
          <span class="title">新建对话</span>
        </button>
        <div class="popover-divider"></div>
        <div
          v-for="conversation in chat.conversations"
          :key="conversation.id"
          class="conversation-item"
          :class="{ active: conversation.id === chat.currentId }"
          role="button"
          tabindex="0"
          @click="selectConversation(conversation.id)"
          @keydown.enter="selectConversation(conversation.id)"
        >
          <span class="title">{{ conversation.title || '新对话' }}</span>
          <span class="time mono">{{ formatDay(conversation.updated_at) }}</span>
          <button
            type="button"
            class="delete"
            title="删除会话"
            aria-label="删除会话"
            @click="removeConversation($event, conversation.id)"
          >
            <Icon name="trash" :size="13" />
          </button>
        </div>
        <div v-if="!chat.conversations.length" class="popover-empty">还没有会话，直接对小球说话吧。</div>
      </div>
    </div>

    <div class="topbar-spacer"></div>

    <span class="status-pill" :title="chatProvider?.base_url || '对话 Provider'">
      <i class="status-dot" :class="providerLevel"></i>
      <span class="status-pill-label">{{ providerLabel }}</span>
    </span>
    <span class="status-pill" :title="voice.statusText">
      <i class="status-dot" :class="voiceLevel"></i>
      <span class="status-pill-label">{{ voiceLabel }}</span>
    </span>

    <div class="topbar-actions">
      <button
        type="button"
        class="icon-btn"
        :class="{ on: ui.transcriptOpen }"
        title="对话记录"
        aria-label="打开对话记录"
        @click="ui.toggleTranscript()"
      >
        <Icon name="chat" />
      </button>
      <button
        type="button"
        class="icon-btn"
        :class="{ on: ui.memoryOpen }"
        title="长期记忆"
        aria-label="打开记忆管理"
        @click="ui.toggleMemory()"
      >
        <Icon name="memory" />
        <span v-if="memoryCount" class="icon-badge mono">{{ memoryCount > 99 ? '99+' : memoryCount }}</span>
      </button>
      <button
        type="button"
        class="icon-btn"
        title="设置"
        aria-label="打开设置"
        @click="ui.openSettings()"
      >
        <Icon name="settings" />
      </button>
    </div>
  </header>
</template>
