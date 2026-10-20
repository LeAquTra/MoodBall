<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { ToolEntry } from '../../lib/types'
import { useToolsStore } from '../../stores/tools'
import { useUiStore } from '../../stores/ui'

const store = useToolsStore()
const ui = useUiStore()

const search = ref('')
const source = ref('all')
const invokeTarget = ref<ToolEntry | null>(null)
const argsText = ref('{}')
const invoking = ref(false)
const result = ref<unknown>(null)
const resultError = ref('')

const filtered = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return store.tools.filter((tool) => {
    if (source.value !== 'all' && tool.source !== source.value) return false
    if (!keyword) return true
    return `${tool.name} ${tool.description} ${tool.server ?? ''}`.toLowerCase().includes(keyword)
  })
})

function schemaText(schema: Record<string, unknown>): string {
  try {
    return JSON.stringify(schema, null, 2)
  } catch {
    return '{}'
  }
}

function exampleArgs(schema: Record<string, unknown>): Record<string, unknown> {
  const properties = (schema.properties ?? {}) as Record<string, { type?: string; default?: unknown; enum?: unknown[] }>
  const required = (schema.required ?? []) as string[]
  const result: Record<string, unknown> = {}
  const keys = required.length ? required : Object.keys(properties)
  for (const key of keys) {
    const property = properties[key] ?? {}
    if (property.default !== undefined) result[key] = property.default
    else if (property.enum?.length) result[key] = property.enum[0]
    else if (property.type === 'number' || property.type === 'integer') result[key] = 0
    else if (property.type === 'boolean') result[key] = false
    else if (property.type === 'array') result[key] = []
    else if (property.type === 'object') result[key] = {}
    else result[key] = ''
  }
  return result
}

function openInvoke(tool: ToolEntry) {
  invokeTarget.value = tool
  argsText.value = JSON.stringify(exampleArgs(tool.input_schema), null, 2)
  result.value = null
  resultError.value = ''
}

async function runInvoke() {
  if (!invokeTarget.value) return
  let args: Record<string, unknown> = {}
  try {
    const parsed = argsText.value.trim() ? JSON.parse(argsText.value) : {}
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('args 必须是 JSON 对象')
    args = parsed
  } catch (error) {
    ui.notify(`args JSON 不合法：${(error as Error).message}`, 'error')
    return
  }
  invoking.value = true
  resultError.value = ''
  try {
    const response = await store.invokeTool(invokeTarget.value.name, args)
    result.value = response?.result ?? response
    if (response?.error) resultError.value = response.error
  } finally {
    invoking.value = false
  }
}

async function toggle(tool: ToolEntry) {
  await store.toggleTool(tool.name, !tool.enabled)
}

onMounted(async () => {
  await store.loadAll()
})
</script>

<template>
  <div>
    <section class="settings-section">
      <div class="row-between">
        <div>
          <h4>刷新与筛选</h4>
          <p class="settings-hint" style="margin-bottom: 0">
            内置 + Python 插件 + MCP 统一注册；Agent 每轮只绑定 top-k。这里可以查看 schema 并直接试运行。
          </p>
        </div>
        <button type="button" class="paper-btn" :disabled="store.refreshing" @click="store.refreshTools()">
          {{ store.refreshing ? '刷新中…' : '刷新工具' }}
        </button>
      </div>
      <div class="row" style="margin-top: 10px; flex-wrap: wrap">
        <input
          v-model="search"
          class="inline-input"
          placeholder="搜索工具名 / 描述"
        />
        <select v-model="source" class="inline-select">
          <option value="all">全部来源</option>
          <option value="builtin">builtin</option>
          <option value="plugin">plugin</option>
          <option value="mcp">mcp</option>
        </select>
      </div>
      <div v-if="store.lastError" class="chat-error" style="margin-top: 8px">{{ store.lastError }}</div>
    </section>

    <section v-if="invokeTarget" class="provider-card">
      <div class="provider-card-head">
        <span class="tool-source" :class="invokeTarget.source">{{ invokeTarget.source }}</span>
        <span class="provider-name mono" style="font-size: 12px">{{ invokeTarget.name }}</span>
        <div class="provider-actions">
          <button type="button" class="ghost-btn" @click="invokeTarget = null">关闭</button>
          <button type="button" class="paper-btn" :disabled="invoking" @click="runInvoke">
            {{ invoking ? '执行中…' : '运行' }}
          </button>
        </div>
      </div>
      <p class="settings-hint">{{ invokeTarget.description || '无描述' }}</p>
      <div class="field">
        <label>参数（JSON）</label>
        <textarea v-model="argsText" rows="6" spellcheck="false"></textarea>
      </div>
      <div v-if="resultError" class="chat-error">{{ resultError }}</div>
      <div v-if="result !== null" class="field">
        <label>结果</label>
        <div class="schema-box">{{ JSON.stringify(result, null, 2) }}</div>
      </div>
    </section>

    <section class="settings-section">
      <h4>已注册工具</h4>
      <div v-for="tool in filtered" :key="tool.name" class="tool-row">
        <div class="tool-row-head">
          <span class="tool-row-name">{{ tool.name }}</span>
          <span class="tool-source" :class="tool.source">{{ tool.source }}</span>
          <span v-if="tool.server" class="muted tiny">{{ tool.server }}</span>
          <span v-if="!tool.enabled" class="badge warn">disabled</span>
          <div class="provider-actions">
            <label v-if="tool.source === 'mcp'" class="row tiny muted">
              <input type="checkbox" :checked="tool.enabled" @change="toggle(tool)" />
              启用
            </label>
            <button type="button" class="ghost-btn" @click="openInvoke(tool)">试运行</button>
          </div>
        </div>
        <div class="tool-row-desc">{{ tool.description || '无描述' }}</div>
        <details style="margin-top: 6px">
          <summary class="tiny muted" style="cursor: pointer">查看 input schema</summary>
          <div class="schema-box" style="margin-top: 6px">{{ schemaText(tool.input_schema) }}</div>
        </details>
      </div>
      <div v-if="!filtered.length" class="empty-note">没有匹配的工具。点「刷新工具」重新发现。</div>
    </section>
  </div>
</template>
