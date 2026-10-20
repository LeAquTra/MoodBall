<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import EmotionBallHost from './EmotionBallHost.vue'
import ComposerBar from './ComposerBar.vue'
import VoiceDock from './VoiceDock.vue'
import StatusBar from './StatusBar.vue'
import Icon from './Icon.vue'
import { useBallStore } from '../stores/ball'
import { useCameraStore } from '../stores/camera'
import { useChatStore } from '../stores/chat'
import { useMemoryStore } from '../stores/memory'
import { useUiStore } from '../stores/ui'
import { useVoiceStore } from '../stores/voice'

const ball = useBallStore()
const camera = useCameraStore()
const chat = useChatStore()
const memory = useMemoryStore()
const ui = useUiStore()
const voice = useVoiceStore()

const clicks = ref(0)
const lastClick = ref(0)
let readyTimer = 0

const SOURCE_LABELS: Record<string, string> = {
  state: '状态',
  rule: '规则',
  llm: '模型',
  interaction: '互动',
}

const lastAssistant = computed(() => {
  for (let index = chat.messages.length - 1; index >= 0; index -= 1) {
    const message = chat.messages[index]
    if (message.role === 'assistant' && message.content.trim()) return message.content.trim()
  }
  return ''
})

const captionMode = computed(() => {
  if (ball.tips) return 'tips'
  if (chat.streaming) return 'live'
  if (lastAssistant.value) return 'last'
  return 'hint'
})

const captionText = computed(() => {
  if (ball.tips) return ball.tips
  if (lastAssistant.value) return lastAssistant.value
  if (voice.active) return voice.statusText
  return '点我一下，或者说句话试试。'
})

const statusLabel = computed(() => {
  if (voice.state === 'error') return '语音异常'
  if (voice.listening) return '正在聆听'
  if (voice.busy) return voice.statusText
  if (chat.streaming) {
    if (chat.status === 'thinking') return '思考中'
    if (chat.status === 'acting') return '处理中'
    if (chat.status === 'speaking') return '说话中'
  }
  if (!ball.ready) return '唤醒中'
  return '待机'
})

const statusLevel = computed(() => {
  if (voice.state === 'error') return 'bad'
  if (voice.listening || voice.busy || chat.streaming) return 'live'
  return ball.ready ? 'ok' : 'idle'
})

const sourceLabel = computed(() => SOURCE_LABELS[ball.lastSource] ?? ball.lastSource)

function onReady() {
  ball.applyEmotion('05', 'state', true)
  window.clearTimeout(readyTimer)
  readyTimer = window.setTimeout(() => {
    if (ball.current === '05') ball.applyEmotion('02', 'state', true)
  }, 1100)
}

function onBallError(payload: unknown) {
  const message = (payload as { message?: string })?.message || '表情引擎异常'
  ui.notify(message, 'error')
  ball.applyEmotion('34', 'state', true)
}

function onBallClick() {
  const now = Date.now()
  if (now - lastClick.value < 700) clicks.value += 1
  else clicks.value = 1
  lastClick.value = now
  ball.api?.resetIdle?.()
  if (clicks.value >= 3) {
    clicks.value = 0
    ball.pet()
    return
  }
  ball.applyEmotion('03', 'interaction')
  ball.setTips(voice.active ? '在听你说…' : '点我三下试试')
}

function onGazeMove(event: MouseEvent) {
  const target = event.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  const nx = Math.max(-1, Math.min(1, ((event.clientX - rect.left) / rect.width) * 2 - 1))
  const ny = Math.max(-1, Math.min(1, ((event.clientY - rect.top) / rect.height) * 2 - 1))
  ball.api?.setGaze?.(nx, ny)
}

function clearGaze() {
  ball.api?.clearGaze?.()
}

async function takeSnapshot() {
  ball.applyEmotion('03', 'interaction')
  const result = await camera.snapshot(chat.currentId ?? undefined)
  if (result) {
    ball.applyEmotion('33', 'rule', true)
    ball.setTips('抓拍成功')
    window.setTimeout(() => ball.applyEmotion('02', 'state', true), 1600)
  } else {
    ball.applyEmotion('34', 'state', true)
  }
}

onBeforeUnmount(() => window.clearTimeout(readyTimer))
</script>

<template>
  <main class="stage">
    <div class="stage-glow" aria-hidden="true"></div>

    <div class="stage-meta">
      <span class="eyebrow">
        <i class="eyebrow-dot" aria-hidden="true"></i>
        桌面陪伴 · 本地运行
      </span>
      <span class="stage-status" role="status" aria-live="polite">
        <i class="status-dot" :class="statusLevel"></i>
        {{ statusLabel }}
      </span>
    </div>

    <section class="core" aria-label="表情小球">
      <div
        class="ball-scene"
        role="button"
        tabindex="0"
        aria-label="和小球互动"
        @click="onBallClick"
        @keydown.enter.prevent="onBallClick"
        @mousemove="onGazeMove"
        @mouseleave="clearGaze"
      >
        <div class="orbit orbit-1" aria-hidden="true"></div>
        <div class="orbit orbit-2" aria-hidden="true"></div>
        <div class="orbit orbit-3" aria-hidden="true"></div>
        <div class="ball-floor" aria-hidden="true"></div>
        <EmotionBallHost class="ball" @ready="onReady" @error="onBallError" />
      </div>

      <div class="caption">
        <div class="caption-head">
          <span class="emotion-id mono">#{{ ball.current }}</span>
          <span class="emotion-name">{{ ball.currentEmotion.name }}</span>
          <span class="caption-divider" aria-hidden="true"></span>
          <span class="caption-source">{{ sourceLabel }}</span>
        </div>
        <p class="caption-text" :class="captionMode" :title="captionText">{{ captionText }}</p>
      </div>

      <ComposerBar />
    </section>

    <div class="dock">
      <VoiceDock />
      <div class="dock-tools">
        <button type="button" class="tool-btn" :disabled="camera.loading" title="抓一帧画面" @click="takeSnapshot">
          <Icon name="snapshot" :size="15" />
          <span>抓拍</span>
        </button>
        <button type="button" class="tool-btn" :class="{ on: ui.cameraOpen }" title="摄像头面板" @click="ui.toggleCamera()">
          <Icon name="camera" :size="15" />
          <span>摄像头</span>
        </button>
        <button type="button" class="tool-btn" :class="{ on: ui.paletteOpen }" title="33 种表情" @click="ui.paletteOpen = true">
          <Icon name="spark" :size="15" />
          <span>表情</span>
        </button>
        <button
          type="button"
          class="tool-btn"
          :class="{ on: ui.memoryOpen }"
          title="长期记忆"
          @click="ui.toggleMemory()"
        >
          <Icon name="memory" :size="15" />
          <span>记忆</span>
          <span class="tool-count mono">{{ memory.stats.total }}</span>
        </button>
      </div>
      <StatusBar />
    </div>
  </main>
</template>
