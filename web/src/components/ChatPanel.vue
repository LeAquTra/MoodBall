<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import ToolCallCard from './ToolCallCard.vue'
import { useBallStore } from '../stores/ball'
import { useChatStore } from '../stores/chat'
import { formatLatency, formatTime } from '../lib/format'

const chat = useChatStore()
const ball = useBallStore()

const scroller = ref<HTMLElement | null>(null)
const stick = ref(true)

const suggestions = [
  '今天有点累，陪我聊两句',
  '看看我桌上是什么',
  '你记得我喜欢什么吗？',
  '记住：我每天早上喝美式',
]

const assistantCount = computed(() => chat.messages.filter((message) => message.role === 'assistant').length)

function emotionLabel(id?: string): string {
  if (!id) return ''
  const emotion = ball.emotions.find((item) => item.id === id)
  return emotion ? `#${id} ${emotion.name}` : `#${id}`
}

function onScroll() {
  const element = scroller.value
  if (!element) return
  stick.value = element.scrollHeight - element.scrollTop - element.clientHeight < 120
}

async function scrollToBottom(force = false) {
  if (!force && !stick.value) return
  await nextTick()
  const element = scroller.value
  if (element) element.scrollTop = element.scrollHeight
}

watch(
  () => chat.messages.length,
  () => scrollToBottom(true),
)
watch(
  () => chat.messages[chat.messages.length - 1]?.content,
  () => scrollToBottom(),
)
watch(
  () => chat.loadingMessages,
  (loading) => {
    if (!loading) scrollToBottom(true)
  },
)

onMounted(() => scrollToBottom(true))

function useSuggestion(text: string) {
  chat.draft = text
}

function clearError() {
  chat.error = null
}
</script>

<template>
  <div class="transcript">
    <div class="transcript-bar">
      <span class="transcript-count mono">{{ assistantCount }} 轮回复</span>
      <span class="transcript-note">所有对话都落在本机 SQLite</span>
    </div>

    <div ref="scroller" class="transcript-scroll" @scroll="onScroll">
      <div v-if="!chat.messages.length && !chat.loadingMessages" class="empty-state">
        <div class="empty-glyph" aria-hidden="true">
          <span class="empty-eye"></span>
          <span class="empty-eye"></span>
        </div>
        <h3>小球醒着</h3>
        <p>文字、语音、摄像头都可以。说「小d小d」唤醒，或者直接在这里打字。</p>
        <div class="suggestions">
          <button
            v-for="suggestion in suggestions"
            :key="suggestion"
            type="button"
            class="suggestion"
            @click="useSuggestion(suggestion)"
          >
            {{ suggestion }}
          </button>
        </div>
      </div>

      <div v-if="chat.loadingMessages" class="empty-state compact">正在加载历史消息…</div>

      <article
        v-for="message in chat.messages"
        :key="message.id"
        class="message"
        :class="[message.role, { failed: message.role === 'assistant' && message.content.includes('没有成功') }]"
      >
        <div class="bubble">
          <template v-if="message.role === 'assistant'">
            <template v-if="message.content">{{ message.content }}</template>
            <span v-if="message.pending && message.content" class="stream-cursor"></span>
            <span v-if="message.pending && !message.content" class="thinking-dots">
              <i></i><i></i><i></i>
            </span>
          </template>
          <template v-else>{{ message.content }}</template>
        </div>

        <div v-if="message.tool_events?.length" class="tool-list">
          <ToolCallCard v-for="(tool, index) in message.tool_events" :key="`${tool.name}-${index}`" :tool="tool" />
        </div>

        <div class="message-meta">
          <span v-if="message.role === 'user'" class="mono">{{ formatTime(message.created_at) }}</span>
          <template v-else>
            <span v-if="message.emotion_id" class="emotion mono">{{ emotionLabel(message.emotion_id) }}</span>
            <span v-if="message.latency_ms">{{ formatLatency(message.latency_ms) }}</span>
            <span v-if="message.tokens_out" class="mono">{{ message.tokens_out }} tok</span>
            <span v-if="message.pending">生成中…</span>
          </template>
        </div>
      </article>
    </div>

    <div v-if="chat.error" class="inline-error">
      <span>{{ chat.error }}</span>
      <button type="button" class="ghost-btn tiny-btn" @click="clearError">知道了</button>
    </div>
  </div>
</template>
