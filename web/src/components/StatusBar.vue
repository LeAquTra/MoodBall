<script setup lang="ts">
import { computed } from 'vue'
import Icon from './Icon.vue'
import { useSettingsStore } from '../stores/settings'
import { formatTime } from '../lib/format'

const settings = useSettingsStore()

type Level = 'ok' | 'warn' | 'bad' | 'idle'

function level(ok: boolean | undefined, warn = false): Level {
  if (ok) return 'ok'
  return warn ? 'warn' : 'bad'
}

const items = computed(() => {
  const health = settings.health
  const providers = health?.providers ?? {}
  return [
    {
      key: 'db',
      label: 'SQLite',
      level: level(health?.db?.ok),
      title: health?.db?.path || health?.db?.error || '',
    },
    {
      key: 'asr',
      label: 'ASR',
      level: level(health?.asr?.ok, settings.meta?.asr_enabled !== false),
      title: health?.asr?.message || health?.asr?.model || '本机 Qwen3-ASR',
    },
    {
      key: 'camera',
      label: '摄像头',
      level: level(health?.camera?.opencv, settings.meta?.camera_enabled !== false),
      title: health?.camera?.message || '',
    },
    {
      key: 'chat',
      label: 'Chat',
      level: level(providers.chat?.configured, true),
      title: providers.chat?.model || '对话 Provider',
    },
    {
      key: 'tts',
      label: 'TTS',
      level: level(providers.tts?.configured && settings.meta?.tts_enabled !== false, true),
      title: providers.tts?.model || 'TTS Provider',
    },
    {
      key: 'mcp',
      label: 'MCP',
      level: level((health?.mcp?.total ?? 0) > 0, true),
      title: `共 ${health?.mcp?.total ?? 0} 个 server，启用 ${health?.mcp?.enabled ?? 0} 个`,
    },
  ]
})

const updated = computed(() =>
  settings.lastHealthAt ? formatTime(new Date(settings.lastHealthAt).toISOString()) : '—',
)
</script>

<template>
  <div class="statusbar" :title="`本地模式 · ${settings.health?.mode || 'personal'} · 更新 ${updated}`">
    <span v-for="item in items" :key="item.key" class="statusbar-item" :title="item.title">
      <i class="status-dot" :class="item.level"></i>
      {{ item.label }}
    </span>
    <button type="button" class="statusbar-refresh" title="刷新健康检查" @click="settings.loadHealth()">
      <Icon name="refresh" :size="11" />
    </button>
  </div>
</template>
