<script setup lang="ts">
import { computed } from 'vue'
import Icon from './Icon.vue'
import type { ToolEvent } from '../lib/types'

const props = defineProps<{ tool: ToolEvent }>()

const statusText = computed(() => {
  if (props.tool.status === 'ok') return 'ok'
  if (props.tool.status === 'timeout') return 'timeout'
  return 'error'
})

const argsText = computed(() => {
  try {
    return JSON.stringify(props.tool.args ?? {}, null, 2)
  } catch {
    return String(props.tool.args ?? '')
  }
})

const resultText = computed(() => {
  if (props.tool.result_preview) return props.tool.result_preview
  if (props.tool.result != null) {
    try {
      return JSON.stringify(props.tool.result, null, 2)
    } catch {
      return String(props.tool.result)
    }
  }
  return ''
})
</script>

<template>
  <details class="tool-card" :class="`status-${statusText}`">
    <summary>
      <Icon name="spark" :size="13" />
      <strong class="mono">{{ tool.name }}</strong>
      <span class="tool-source" :class="tool.source">{{ tool.source }}</span>
      <span v-if="tool.server" class="dim mono">{{ tool.server }}</span>
      <span class="badge" :class="tool.status === 'ok' ? 'ok' : tool.status === 'timeout' ? 'warn' : 'bad'">
        {{ statusText }}
      </span>
      <span class="duration mono">{{ tool.duration_ms }} ms</span>
    </summary>
    <div class="tool-body">
      <div v-if="argsText && argsText !== '{}'" class="tool-block">
        <span class="block-label">参数</span>
        <div class="schema-box">{{ argsText }}</div>
      </div>
      <div v-if="resultText" class="tool-block">
        <span class="block-label">结果</span>
        <div class="schema-box">{{ resultText }}</div>
      </div>
    </div>
  </details>
</template>
