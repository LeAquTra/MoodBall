<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api } from '../../lib/api'
import type { McpServer } from '../../lib/types'
import { useToolsStore } from '../../stores/tools'
import { useUiStore } from '../../stores/ui'

const store = useToolsStore()
const ui = useUiStore()

interface ServerForm {
  name: string
  transport: string
  command: string
  argsText: string
  envText: string
  url: string
  headersText: string
  tool_prefix: string
  enabled: boolean
  auto_start: boolean
  timeout_s: number
}

const blank = (): ServerForm => ({
  name: '',
  transport: 'stdio',
  command: 'npx.cmd',
  argsText: '[\n  "-y",\n  "@modelcontextprotocol/server-filesystem",\n  "E:/Pycharm/Project/MoodBall"\n]',
  envText: '{}',
  url: '',
  headersText: '{}',
  tool_prefix: '',
  enabled: true,
  auto_start: true,
  timeout_s: 30,
})

const form = reactive<ServerForm>(blank())
const editingId = ref<string | null>(null)
const showEditor = ref(false)
const saving = ref(false)

function startCreate() {
  Object.assign(form, blank())
  editingId.value = null
  showEditor.value = true
}

function startEdit(server: McpServer) {
  Object.assign(form, {
    name: server.name,
    transport: server.transport,
    command: server.command,
    argsText: JSON.stringify(server.args ?? [], null, 2),
    envText: JSON.stringify(server.env ?? {}, null, 2),
    url: server.url,
    headersText: JSON.stringify(server.headers ?? {}, null, 2),
    tool_prefix: server.tool_prefix,
    enabled: server.enabled,
    auto_start: server.auto_start,
    timeout_s: server.timeout_s,
  })
  editingId.value = server.id
  showEditor.value = true
}

function cancel() {
  showEditor.value = false
  editingId.value = null
}

function parseJson(text: string, fallback: unknown): unknown {
  if (!text.trim()) return fallback
  return JSON.parse(text)
}

async function save() {
  if (!form.name.trim()) {
    ui.notify('name 不能为空', 'warning')
    return
  }
  let args: unknown
  let env: unknown
  let headers: unknown
  try {
    args = parseJson(form.argsText, [])
    env = parseJson(form.envText, {})
    headers = parseJson(form.headersText, {})
    if (!Array.isArray(args)) throw new Error('args 必须是 JSON 数组')
    if (!env || typeof env !== 'object' || Array.isArray(env)) throw new Error('env 必须是 JSON 对象')
    if (!headers || typeof headers !== 'object' || Array.isArray(headers)) throw new Error('headers 必须是 JSON 对象')
  } catch (error) {
    ui.notify(`JSON 不合法：${(error as Error).message}`, 'error')
    return
  }
  if (form.transport === 'stdio' && !form.command.trim()) {
    ui.notify('stdio 必须填写 command', 'warning')
    return
  }
  if (form.transport !== 'stdio' && !form.url.trim()) {
    ui.notify('http / sse 必须填写 URL', 'warning')
    return
  }
  const payload = {
    name: form.name.trim(),
    transport: form.transport,
    command: form.command.trim(),
    args,
    env,
    url: form.url.trim(),
    headers,
    tool_prefix: form.tool_prefix.trim(),
    enabled: form.enabled,
    auto_start: form.auto_start,
    timeout_s: form.timeout_s,
  }
  saving.value = true
  try {
    if (editingId.value) await store.updateServer(editingId.value, payload)
    else await store.createServer(payload)
    cancel()
  } finally {
    saving.value = false
  }
}

async function remove(server: McpServer) {
  if (!window.confirm(`删除 MCP server「${server.name}」？`)) return
  await store.deleteServer(server.id)
}

async function toggleEnabled(server: McpServer) {
  await store.updateServer(server.id, { enabled: !server.enabled })
}

async function importConfig() {
  try {
    const result = await api.importMcp({})
    ui.notify(`从 mcp_servers.json 导入 ${result.imported} 个 server`, 'success')
    await Promise.allSettled([store.loadServers(), store.loadTools()])
  } catch (error) {
    ui.notify((error as Error).message, 'error')
  }
}

async function exportConfig() {
  try {
    const result = await api.exportMcp()
    const blob = new Blob([JSON.stringify(result.config, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'mcp_servers.json'
    anchor.click()
    URL.revokeObjectURL(url)
    ui.notify('已导出 mcp_servers.json', 'success')
  } catch (error) {
    ui.notify((error as Error).message, 'error')
  }
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
          <h4>连接与发现</h4>
          <p class="settings-hint" style="margin-bottom: 0">
            stdio / http / sse 统一接入 ToolRegistry；工具名自动加 `mcp__{server}__` 命名空间。Windows 下
            npx / uvx 用 `.cmd` / `.exe`，后端会解析绝对路径。
          </p>
        </div>
        <div class="row">
          <button type="button" class="ghost-btn" @click="importConfig">导入</button>
          <button type="button" class="ghost-btn" @click="exportConfig">导出</button>
          <button type="button" class="paper-btn" @click="startCreate">＋ 添加</button>
        </div>
      </div>
    </section>

    <section v-if="showEditor" class="provider-card">
      <div class="provider-card-head">
        <span class="provider-kind">{{ form.transport }}</span>
        <span class="provider-name">{{ editingId ? '编辑 MCP server' : '新增 MCP server' }}</span>
        <div class="provider-actions">
          <button type="button" class="ghost-btn" @click="cancel">取消</button>
          <button type="button" class="paper-btn" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
      <div class="field-grid">
        <div class="field">
          <label>名称（也是命名空间）</label>
          <input v-model="form.name" placeholder="filesystem" />
        </div>
        <div class="field">
          <label>Transport</label>
          <select v-model="form.transport">
            <option value="stdio">stdio</option>
            <option value="http">http</option>
            <option value="sse">sse</option>
          </select>
        </div>
      </div>

      <template v-if="form.transport === 'stdio'">
        <div class="field">
          <label>Command</label>
          <input v-model="form.command" placeholder="npx.cmd / uvx.exe / python" />
        </div>
        <div class="field">
          <label>Args（JSON 数组）</label>
          <textarea v-model="form.argsText" rows="5" spellcheck="false"></textarea>
        </div>
        <div class="field">
          <label>Env（JSON 对象）</label>
          <textarea v-model="form.envText" rows="3" spellcheck="false"></textarea>
        </div>
      </template>
      <template v-else>
        <div class="field">
          <label>URL</label>
          <input v-model="form.url" placeholder="http://127.0.0.1:8931/mcp" />
        </div>
        <div class="field">
          <label>Headers（JSON 对象）</label>
          <textarea v-model="form.headersText" rows="3" spellcheck="false"></textarea>
        </div>
      </template>

      <div class="field-grid">
        <div class="field">
          <label>工具前缀（可选）</label>
          <input v-model="form.tool_prefix" placeholder="留空 = mcp__{name}__" />
        </div>
        <div class="field">
          <label>超时（秒）</label>
          <input v-model.number="form.timeout_s" type="number" min="1" max="300" />
        </div>
      </div>
      <div class="row" style="gap: 16px">
        <label class="row tiny muted"><input v-model="form.enabled" type="checkbox" /> enabled</label>
        <label class="row tiny muted"><input v-model="form.auto_start" type="checkbox" /> auto_start</label>
      </div>
    </section>

    <section class="settings-section">
      <h4>服务列表</h4>
      <div v-for="server in store.servers" :key="server.id" class="tool-row">
        <div class="tool-row-head">
          <strong>{{ server.name }}</strong>
          <span class="tool-source mcp">{{ server.transport }}</span>
          <span class="badge" :class="server.enabled ? 'ok' : ''">{{ server.enabled ? 'enabled' : 'disabled' }}</span>
          <span class="badge">{{ server.tool_count ?? server.tools?.length ?? 0 }} tools</span>
          <span v-if="server.last_error" class="badge bad">error</span>
          <div class="provider-actions">
            <button type="button" class="ghost-btn" @click="store.testServer(server.id)">测试</button>
            <button type="button" class="ghost-btn" @click="store.refreshServer(server.id)">刷新</button>
            <button type="button" class="ghost-btn" @click="startEdit(server)">编辑</button>
            <button type="button" class="ghost-btn" @click="toggleEnabled(server)">
              {{ server.enabled ? '停用' : '启用' }}
            </button>
            <button type="button" class="ghost-btn danger" @click="remove(server)">删除</button>
          </div>
        </div>
        <div class="code-text" style="margin-top: 5px">
          {{ server.transport === 'stdio' ? `${server.command} ${(server.args || []).join(' ')}` : server.url }}
        </div>
        <div v-if="server.last_error" class="chat-error" style="margin-top: 6px">{{ server.last_error }}</div>
        <details v-if="server.tools?.length" style="margin-top: 6px">
          <summary class="tiny muted" style="cursor: pointer">查看 {{ server.tools.length }} 个工具</summary>
          <div class="stack" style="margin-top: 6px">
            <div v-for="tool in server.tools" :key="tool.id" class="tiny">
              <span class="mono">{{ tool.name }}</span>
              <span class="muted"> · {{ tool.description || '无描述' }}</span>
            </div>
          </div>
        </details>
      </div>
      <div v-if="!store.servers.length" class="empty-note">
        还没有 MCP server。可以直接编辑 <span class="mono">mcp_servers.json</span> 后点「导入」。
      </div>
    </section>
  </div>
</template>
