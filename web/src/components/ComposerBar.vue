<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import Icon from './Icon.vue'
import { useBallStore } from '../stores/ball'
import { useChatStore } from '../stores/chat'
import { useSettingsStore } from '../stores/settings'
import { useUiStore } from '../stores/ui'
import { playAudio, unlockAudio } from '../audio/ttsPlayer'

const ball = useBallStore()
const chat = useChatStore()
const settings = useSettingsStore()
const ui = useUiStore()

const input = ref<HTMLTextAreaElement | null>(null)
const speakOn = computed(() => settings.settings?.speak_replies ?? true)

function autoResize() {
  const element = input.value
  if (!element) return
  element.style.height = 'auto'
  element.style.height = `${Math.min(132, element.scrollHeight)}px`
}

async function send() {
  const content = chat.draft.trim()
  if (!content || chat.streaming) return
  chat.draft = ''
  await nextTick()
  autoResize()
  const speak = speakOn.value
  if (speak) await unlockAudio()
  await chat.sendMessage(content, {
    speak,
    withVision: chat.visionMode,
    handlers: {
      onAudio: (url) => {
        if (speak) void playAudio(url)
      },
    },
  })
}

function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  void send()
}

async function toggleSpeak() {
  const next = !speakOn.value
  await settings.save({ speak_replies: next })
  if (next) await unlockAudio()
  ui.notify(next ? '回复会自动播报' : '已关闭自动播报', 'info')
}

function stop() {
  chat.stop()
  window.setTimeout(() => {
    if (!chat.streaming) ball.applyEmotion('02', 'state', true)
  }, 900)
}
</script>

<template>
  <form class="composer" @submit.prevent="send">
    <textarea
      ref="input"
      v-model="chat.draft"
      rows="1"
      placeholder="和小球说点什么…"
      aria-label="输入消息"
      @input="autoResize"
      @keydown="onKeydown"
    ></textarea>
    <div class="composer-bar">
      <button
        type="button"
        class="chip"
        :class="{ on: chat.visionMode }"
        :title="chat.visionMode ? '这一轮会先抓一帧再回答' : '需要看画面时再打开'"
        @click="chat.visionMode = !chat.visionMode"
      >
        <Icon name="eye" :size="13" />
        视觉{{ chat.visionMode ? '开' : '关' }}
      </button>
      <button type="button" class="chip" :class="{ on: speakOn }" title="是否朗读回复" @click="toggleSpeak">
        <Icon name="volume" :size="13" />
        播报{{ speakOn ? '开' : '关' }}
      </button>
      <span class="composer-hint">Enter 发送 · Shift+Enter 换行 · 空格按住说话</span>
      <button v-if="chat.streaming" type="button" class="chip stop" title="停止生成" @click="stop">
        <Icon name="stop" :size="12" />
        停止
      </button>
      <button
        type="submit"
        class="send-btn"
        :disabled="chat.streaming || !chat.draft.trim()"
        aria-label="发送"
        title="发送"
      >
        <Icon name="send" :size="15" :stroke="1.8" />
      </button>
    </div>
  </form>
</template>
