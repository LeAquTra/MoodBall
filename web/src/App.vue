<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import TopBar from './components/TopBar.vue'
import BallStage from './components/BallStage.vue'
import ChatDrawer from './components/ChatDrawer.vue'
import MemoryDrawer from './components/MemoryDrawer.vue'
import CameraPanel from './components/CameraPanel.vue'
import EmotionPalette from './components/EmotionPalette.vue'
import SettingsDialog from './components/SettingsDialog.vue'
import ToastStack from './components/ToastStack.vue'
import { useChatStore } from './stores/chat'
import { useMemoryStore } from './stores/memory'
import { useSettingsStore } from './stores/settings'
import { useUiStore } from './stores/ui'
import { useVoiceStore } from './stores/voice'
import { stopAudio } from './audio/ttsPlayer'

const ui = useUiStore()
const chat = useChatStore()
const settings = useSettingsStore()
const voice = useVoiceStore()
const memory = useMemoryStore()

let healthTimer = 0

onMounted(() => {
  openFromQuery()
  void settings.loadAll()
  void chat.loadConversations(true)
  void memory.load({ silent: true })
  healthTimer = window.setInterval(() => {
    void settings.loadHealth()
  }, 30000)
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('keyup', onKeyup)
})

/** 深链：?open=memory|chat|camera|palette|settings&tab=memory 便于分享与截图。 */
function openFromQuery() {
  const params = new URLSearchParams(window.location.search)
  const target = params.get('open')
  if (target === 'memory') ui.memoryOpen = true
  else if (target === 'chat') ui.transcriptOpen = true
  else if (target === 'camera') ui.cameraOpen = true
  else if (target === 'palette') ui.paletteOpen = true
  else if (target === 'settings') {
    const tab = params.get('tab')
    const allowed = ['providers', 'mcp', 'tools', 'voice', 'memory', 'privacy'] as const
    const match = allowed.find((item) => item === tab)
    ui.openSettings(match ?? 'providers')
  }
}

onBeforeUnmount(() => {
  window.clearInterval(healthTimer)
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('keyup', onKeyup)
  void voice.stop()
})

function onKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null
  const typing = Boolean(target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
  if (event.key === 'Escape') {
    if (ui.closeTopLayer()) return
    stopAudio()
    return
  }
  if (event.code === 'Space' && !typing && !event.repeat && !ui.settingsOpen) {
    event.preventDefault()
    void voice.pttStart()
  }
}

function onKeyup(event: KeyboardEvent) {
  if (event.code === 'Space' && voice.active) {
    const target = event.target as HTMLElement | null
    if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
    voice.pttStop()
  }
}
</script>

<template>
  <div class="app-shell">
    <TopBar />
    <BallStage />
    <ChatDrawer v-if="ui.transcriptOpen" />
    <MemoryDrawer v-if="ui.memoryOpen" />
    <CameraPanel v-if="ui.cameraOpen" />
    <EmotionPalette v-if="ui.paletteOpen" />
    <SettingsDialog v-if="ui.settingsOpen" />
    <ToastStack />
  </div>
</template>
