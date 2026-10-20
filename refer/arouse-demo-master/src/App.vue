<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import TopBar from './components/TopBar.vue'
import VoiceConsole from './components/VoiceConsole.vue'
import CommandGrid from './components/CommandGrid.vue'
import SettingsDialog from './components/SettingsDialog.vue'
import { useAssistant } from './composables/useAssistant'
import { logs, panels, pushLog, toast } from './store'

const { simulateWake, focusInput, dispose } = useAssistant()

function onKeydown(event: KeyboardEvent) {
  const key = event.key.toLowerCase()

  // Ctrl+Shift+W 在 Chromium 里会关闭窗口，改用 F2
  if (key === 'f2') {
    event.preventDefault()
    simulateWake()
    return
  }

  if ((event.ctrlKey || event.metaKey) && key === 'k') {
    event.preventDefault()
    focusInput()
    return
  }

  if (event.key === 'Escape' && panels.settings) {
    panels.settings = false
  }
}

onMounted(() => {
  if (!logs.value.length) pushLog('system', '控制台就绪 · 点击麦克风开启语音')
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  dispose()
})
</script>

<template>
  <div id="top" class="app">
    <TopBar />

    <main class="page">
      <section class="hero">
        <div class="hero-copy">
          <p class="eyebrow">
            <span class="eyebrow-dot" />
            VOICE INTERFACE / 001
          </p>

          <h1>用一句话，<br />唤醒你的界面。</h1>

          <p class="lede">
            说「小d小d」唤醒，再说「切换主题」。十条指令全部在浏览器里执行，不需要后端。
          </p>

          <div class="hero-meta">
            <span class="pill mono">WAKE WORD · 小d小d</span>
            <span class="pill mono">COMMANDS · 10</span>
            <span class="pill mono">ASR · LOCAL VOSK</span>
          </div>

          <p class="hero-note">
            离线模型在本机运行，唤醒与识别都不上传音频；播报使用系统语音。
          </p>
        </div>

        <VoiceConsole />
      </section>

      <section id="commands" class="section">
        <div class="section-head">
          <div>
            <p class="eyebrow">COMMANDS</p>
            <h2>内置指令</h2>
          </div>
          <p class="section-note">点击卡片直接执行，也可以先唤醒再说出指令。</p>
        </div>
        <CommandGrid />
      </section>

      <section id="about" class="section">
        <div class="section-head">
          <div>
            <p class="eyebrow">MECHANISM</p>
            <h2>它怎么工作</h2>
          </div>
          <p class="section-note">三步：持续匹配唤醒词 → 单次识别指令 → 本地执行动作。</p>
        </div>

        <div class="mechanism">
          <div class="mech-row">
            <span class="mech-idx mono">01</span>
            <span class="mech-title">唤醒</span>
            <p class="mech-text">
              麦克风持续送入本地 Vosk 模型，识别文本命中「小d小d」及其同音变体（小弟 / 小滴 / 小丁），即进入指令态。
            </p>
          </div>
          <div class="mech-row">
            <span class="mech-idx mono">02</span>
            <span class="mech-title">指令</span>
            <p class="mech-text">
              单次识别拿到一句话，先做标点与空格归一化，再用「包含 + 编辑距离」混合打分匹配指令别名。
            </p>
          </div>
          <div class="mech-row">
            <span class="mech-idx mono">03</span>
            <span class="mech-title">执行</span>
            <p class="mech-text">
              命中的指令直接操作 Vue 状态：切换主题、清空记录、打开设置，或滚动到指定区域。
            </p>
          </div>
        </div>
      </section>
    </main>

    <footer class="footer">
      <div class="footer-inner">
        <span>AROUSE · VOICE WAKE DEMO</span>
        <span>DESIGN REFERENCE · DESIGN.MD</span>
        <span>V0.1.0</span>
      </div>
    </footer>

    <SettingsDialog />

    <Transition name="toast">
      <div v-if="toast" :key="toast.id" class="toast" role="status">{{ toast.message }}</div>
    </Transition>
  </div>
</template>
