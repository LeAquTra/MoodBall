<script setup lang="ts">
import ChatPanel from './ChatPanel.vue'
import Icon from './Icon.vue'
import { useChatStore } from '../stores/chat'
import { useUiStore } from '../stores/ui'

const chat = useChatStore()
const ui = useUiStore()

function close() {
  ui.transcriptOpen = false
}

async function newConversation() {
  await chat.newConversation()
}
</script>

<template>
  <div class="drawer-layer" @click.self="close">
    <aside class="drawer drawer-chat" role="dialog" aria-modal="false" aria-label="对话记录">
      <header class="drawer-head">
        <div class="drawer-title">
          <h2>对话记录</h2>
          <span class="drawer-sub">
            {{ chat.currentConversation?.title || '新对话' }} · {{ chat.messages.length }} 条消息
          </span>
        </div>
        <div class="drawer-actions">
          <button type="button" class="icon-btn" title="新建对话" aria-label="新建对话" @click="newConversation">
            <Icon name="plus" />
          </button>
          <button type="button" class="icon-btn" title="关闭" aria-label="关闭对话记录" @click="close">
            <Icon name="close" />
          </button>
        </div>
      </header>
      <ChatPanel />
    </aside>
  </div>
</template>
