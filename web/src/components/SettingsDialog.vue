<script setup lang="ts">
import { computed } from 'vue'
import Icon from './Icon.vue'
import McpSettings from './settings/McpSettings.vue'
import MemorySettings from './settings/MemorySettings.vue'
import PrivacySettings from './settings/PrivacySettings.vue'
import ProviderSettings from './settings/ProviderSettings.vue'
import ToolsPanel from './settings/ToolsPanel.vue'
import VoiceSettings from './settings/VoiceSettings.vue'
import { useUiStore } from '../stores/ui'

const ui = useUiStore()

const tabs = [
  { key: 'providers', label: '模型 Provider' },
  { key: 'mcp', label: 'MCP Servers' },
  { key: 'tools', label: '工具注册表' },
  { key: 'voice', label: '语音与唤醒' },
  { key: 'memory', label: '长期记忆' },
  { key: 'privacy', label: '隐私与数据' },
] as const

const title = computed(() => tabs.find((tab) => tab.key === ui.settingsTab)?.label ?? '设置')

function close() {
  ui.closeSettings()
}
</script>

<template>
  <div class="modal-layer" @click.self="close">
    <div class="settings-modal" role="dialog" aria-modal="true" aria-label="MoodBall 设置">
      <nav class="settings-nav">
        <div class="settings-nav-head">
          <h2>设置</h2>
          <span class="mono">MOODBALL · LOCAL</span>
        </div>
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="settings-tab"
          :class="{ on: ui.settingsTab === tab.key }"
          @click="ui.settingsTab = tab.key"
        >
          {{ tab.label }}
        </button>
        <div class="settings-nav-foot">
          <p>个人本机信任模型：不登录、不审批。服务只绑在 127.0.0.1。</p>
        </div>
      </nav>

      <div class="settings-main">
        <header class="settings-head">
          <div>
            <h3>{{ title }}</h3>
            <span class="settings-crumb mono">settings / {{ ui.settingsTab }}</span>
          </div>
          <button type="button" class="icon-btn" aria-label="关闭设置" title="关闭" @click="close">
            <Icon name="close" />
          </button>
        </header>
        <div class="settings-body">
          <ProviderSettings v-if="ui.settingsTab === 'providers'" />
          <McpSettings v-else-if="ui.settingsTab === 'mcp'" />
          <ToolsPanel v-else-if="ui.settingsTab === 'tools'" />
          <VoiceSettings v-else-if="ui.settingsTab === 'voice'" />
          <MemorySettings v-else-if="ui.settingsTab === 'memory'" />
          <PrivacySettings v-else />
        </div>
      </div>
    </div>
  </div>
</template>
