<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAssistant } from '../composables/useAssistant'
import { panels, theme, ttsEnabled } from '../store'

const { engine } = useAssistant()

const ENGINE_LABEL: Record<string, string> = {
  vosk: 'VOSK LOCAL',
  webspeech: 'WEB SPEECH',
  keyboard: 'KEYBOARD',
}

const ENGINE_NOTE: Record<string, string> = {
  vosk: '离线模型 · 音频不出设备',
  webspeech: '浏览器内置识别 · 依赖厂商云服务',
  keyboard: '键盘演示模式',
}

const engineLabel = computed(() => ENGINE_LABEL[engine.value] ?? 'KEYBOARD')
const engineNote = computed(() => ENGINE_NOTE[engine.value] ?? '')

const dialog = ref<HTMLDialogElement | null>(null)

watch(
  () => panels.settings,
  (open) => {
    const element = dialog.value
    if (!element) return
    if (open && !element.open) element.showModal()
    if (!open && element.open) element.close()
  },
)

function close() {
  panels.settings = false
}
</script>

<template>
  <dialog ref="dialog" class="dialog" @close="panels.settings = false" @click.self="close">
    <header class="dialog-head">
      <h2 class="dialog-title">设置</h2>
      <button class="icon-btn" type="button" aria-label="关闭设置" @click="close">
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
        </svg>
      </button>
    </header>

    <div class="dialog-body">
      <div class="row">
        <div class="row-label">
          <span class="row-title">外观</span>
          <span class="row-note">午夜是默认外观，日光为演示用的浅色映射</span>
        </div>
        <div class="seg" role="group" aria-label="主题">
          <button type="button" :class="{ active: theme === 'dark' }" @click="theme = 'dark'">午夜</button>
          <button type="button" :class="{ active: theme === 'light' }" @click="theme = 'light'">日光</button>
        </div>
      </div>

      <div class="row">
        <div class="row-label">
          <span class="row-title">语音播报</span>
          <span class="row-note">指令执行后用 TTS 读出回复</span>
        </div>
        <button
          class="switch"
          type="button"
          role="switch"
          :class="{ on: ttsEnabled }"
          :aria-checked="ttsEnabled"
          aria-label="语音播报"
          @click="ttsEnabled = !ttsEnabled"
        />
      </div>

      <div class="row">
        <div class="row-label">
          <span class="row-title">唤醒词</span>
          <span class="row-note">同音字也算：小弟 / 小滴 / 小丁 / 小的</span>
        </div>
        <span class="mono">小d小d</span>
      </div>

      <div class="row">
        <div class="row-label">
          <span class="row-title">识别引擎</span>
          <span class="row-note">{{ engineNote }}</span>
        </div>
        <span class="mono">{{ engineLabel }}</span>
      </div>

      <p class="dialog-note">
        默认使用本地 Vosk 模型（约 42MB，首次加载需要几秒）。模型加载失败或麦克风被拒时，会回退到浏览器识别；
        仍不可用则进入键盘模式：先按 <code class="mono">F2</code> 模拟唤醒，再输入指令。
      </p>
    </div>
  </dialog>
</template>
