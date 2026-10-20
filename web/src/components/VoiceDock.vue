<script setup lang="ts">
import { computed, ref } from 'vue'
import Icon from './Icon.vue'
import { useVoiceStore } from '../stores/voice'
import { stopAudio } from '../audio/ttsPlayer'

const voice = useVoiceStore()
const pttPressed = ref(false)

const micClass = computed(() => ({
  active: voice.active,
  listening: voice.listening,
  busy: voice.busy,
  error: voice.state === 'error',
  muted: voice.muted,
}))

const bars = Array.from({ length: 14 }, (_, index) => index)

function barHeight(index: number): string {
  const wave = Math.abs(Math.sin(index * 0.82 + 0.4))
  const energy = voice.level * (0.55 + Math.abs(Math.cos(index * 0.61)) * 0.45)
  const base = voice.listening || voice.busy ? 0.18 : 0.08
  return `${Math.round(3 + (wave * 0.35 + energy * 0.9 + base) * 18)}px`
}

async function toggle() {
  await voice.toggle()
}

async function onPttStart() {
  pttPressed.value = true
  await voice.pttStart()
}

function onPttStop() {
  if (!pttPressed.value) return
  pttPressed.value = false
  voice.pttStop()
}
</script>

<template>
  <div class="voice-dock">
    <button
      type="button"
      class="mic-btn"
      :class="micClass"
      :aria-pressed="voice.active"
      :aria-label="voice.active ? '关闭语音' : '开启语音'"
      :title="voice.active ? '关闭语音' : '开启语音（也可按住空格说话）'"
      @click="toggle"
    >
      <span class="mic-ring" aria-hidden="true"></span>
      <Icon :name="voice.muted ? 'mic-off' : 'mic'" :size="18" :stroke="1.7" />
    </button>

    <div class="voice-meter" aria-hidden="true">
      <span v-for="index in bars" :key="index" :style="{ height: barHeight(index) }"></span>
    </div>

    <button
      type="button"
      class="ptt-btn"
      :class="{ pressed: pttPressed }"
      @pointerdown.prevent="onPttStart"
      @pointerup="onPttStop"
      @pointerleave="onPttStop"
      @pointercancel="onPttStop"
    >
      {{ pttPressed ? '松开发送' : '按住说话' }}
    </button>

    <button
      v-if="voice.active"
      type="button"
      class="ghost-btn tiny-btn"
      :title="voice.muted ? '取消静音' : '静音麦克风'"
      @click="voice.toggleMute()"
    >
      {{ voice.muted ? '取消静音' : '静音' }}
    </button>

    <button
      v-if="voice.state === 'speaking'"
      type="button"
      class="ghost-btn tiny-btn"
      @click="stopAudio()"
    >
      停止播报
    </button>
  </div>
</template>
