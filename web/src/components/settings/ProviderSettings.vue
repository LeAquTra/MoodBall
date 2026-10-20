<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../../lib/api'
import type { Provider } from '../../lib/types'
import { useSettingsStore } from '../../stores/settings'
import { useUiStore } from '../../stores/ui'

const settings = useSettingsStore()
const ui = useUiStore()

const kinds = [
  {
    key: 'chat',
    label: '对话 Chat',
    hint: 'DeepSeek / 任意 OpenAI-compatible。Base URL 填到域名或 /v1，不要带 /chat/completions。',
  },
  {
    key: 'vision',
    label: '视觉 Vision',
    hint: '智谱 GLM-4.6V 等 OpenAI-compatible 视觉模型。图片会以 base64 data URI 发送。',
  },
  {
    key: 'tts',
    label: '语音合成 TTS',
    hint: '百炼 Qwen3-TTS / CosyVoice。extra 里可写 protocol、voice、format、sample_rate。',
  },
  {
    key: 'asr',
    label: '语音识别 ASR',
    hint: '本机 Qwen3-ASR 服务地址；不需要云 Key。修改后重启语音会话生效。',
  },
]

interface ProviderForm {
  kind: string
  name: string
  base_url: string
  model: string
  api_key: string
  extraText: string
  enabled: boolean
  is_default: boolean
}

const blank = (kind: string): ProviderForm => ({
  kind,
  name: kind === 'chat' ? 'DeepSeek' : kind === 'vision' ? '智谱视觉' : kind === 'tts' ? '百炼 TTS' : '本机 ASR',
  base_url:
    kind === 'chat'
      ? 'https://api.deepseek.com'
      : kind === 'vision'
        ? 'https://open.bigmodel.cn/api/paas/v4'
        : kind === 'tts'
          ? 'https://dashscope.aliyuncs.com/api/v1'
          : 'http://127.0.0.1:9100',
  model:
    kind === 'chat'
      ? 'deepseek-flash'
      : kind === 'vision'
        ? 'glm-4.6v-flash'
        : kind === 'tts'
          ? 'qwen3-tts-flash'
          : 'Qwen/Qwen3-ASR-0.6B',
  api_key: '',
  extraText:
    kind === 'tts'
      ? JSON.stringify({ protocol: 'dashscope-mm', voice: 'Cherry', format: 'wav', sample_rate: 24000 }, null, 2)
      : '{}',
  enabled: true,
  is_default: false,
})

const form = reactive<ProviderForm>(blank('chat'))
const editingId = ref<string | null>(null)
const creatingKind = ref<string | null>(null)
const showEditor = ref(false)
const showKey = ref(false)
const saving = ref(false)
const revealed = ref<Record<string, string>>({})

const editingProvider = computed(() => settings.providers.find((item) => item.id === editingId.value) ?? null)
const editorTitle = computed(() => (editingId.value ? '编辑 Provider' : '新增 Provider'))

function byKind(kind: string): Provider[] {
  return settings.providers.filter((provider) => provider.kind === kind)
}

function startCreate(kind: string) {
  editingId.value = null
  creatingKind.value = kind
  Object.assign(form, blank(kind))
  showEditor.value = true
  showKey.value = false
}

function startEdit(provider: Provider) {
  editingId.value = provider.id
  creatingKind.value = null
  Object.assign(form, {
    kind: provider.kind,
    name: provider.name,
    base_url: provider.base_url,
    model: provider.model,
    api_key: '',
    extraText: JSON.stringify(provider.extra ?? {}, null, 2),
    enabled: provider.enabled,
    is_default: provider.is_default,
  })
  showEditor.value = true
  showKey.value = false
}

function cancelEdit() {
  showEditor.value = false
  editingId.value = null
  creatingKind.value = null
}

async function save() {
  if (!form.name.trim() || !form.base_url.trim() || !form.model.trim()) {
    ui.notify('name / Base URL / 模型都要填写', 'warning')
    return
  }
  let extra: Record<string, unknown> = {}
  try {
    extra = form.extraText.trim() ? JSON.parse(form.extraText) : {}
    if (!extra || typeof extra !== 'object' || Array.isArray(extra)) throw new Error('extra 必须是 JSON 对象')
  } catch (error) {
    ui.notify(`extra JSON 不合法：${(error as Error).message}`, 'error')
    return
  }
  const payload: Record<string, unknown> = {
    kind: form.kind,
    name: form.name.trim(),
    base_url: form.base_url.trim(),
    model: form.model.trim(),
    extra,
    enabled: form.enabled,
    is_default: form.is_default,
  }
  if (form.api_key) payload.api_key = form.api_key
  saving.value = true
  try {
    if (editingId.value) await settings.updateProvider(editingId.value, payload)
    else await settings.createProvider(payload)
    await settings.loadProviders(settings.revealKeys)
    cancelEdit()
  } finally {
    saving.value = false
  }
}

async function remove(provider: Provider) {
  if (!window.confirm(`删除 Provider「${provider.name}」？`)) return
  await settings.deleteProvider(provider.id)
}

async function toggleEnabled(provider: Provider) {
  await settings.updateProvider(provider.id, { enabled: !provider.enabled })
}

async function makeDefault(provider: Provider) {
  await settings.updateProvider(provider.id, { is_default: true })
}

async function test(provider: Provider) {
  await settings.testProvider(provider.id)
}

async function revealKeys() {
  await settings.revealAllKeys()
  const result = await api.providers(true)
  revealed.value = Object.fromEntries(result.items.map((item) => [item.id, item.api_key]))
  ui.notify('已显示 Key（本机明文，注意不要截图外传）', 'warning')
}

onMounted(async () => {
  await settings.loadProviders()
})
</script>

<template>
  <div>
    <section class="settings-section">
      <div class="row-between">
        <div>
          <h4>能力 Provider</h4>
          <p class="settings-hint" style="margin-bottom: 0">
            数据库里的配置优先于 .env；空 Key = 保留原值，填写新值才会覆盖。个人本机模式，Key 明文存 SQLite。
          </p>
        </div>
        <button type="button" class="ghost-btn" @click="revealKeys">显示已保存 Key</button>
      </div>
    </section>

    <section v-if="showEditor" class="provider-card">
      <div class="provider-card-head">
        <span class="provider-kind">{{ form.kind }}</span>
        <span class="provider-name">{{ editorTitle }}</span>
        <div class="provider-actions">
          <button type="button" class="ghost-btn" @click="cancelEdit">取消</button>
          <button type="button" class="paper-btn" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
      <div class="field-grid">
        <div class="field">
          <label>名称</label>
          <input v-model="form.name" maxlength="80" />
        </div>
        <div class="field">
          <label>模型</label>
          <input v-model="form.model" maxlength="200" />
        </div>
      </div>
      <div class="field">
        <label>Base URL</label>
        <input v-model="form.base_url" placeholder="https://api.deepseek.com" />
      </div>
      <div class="field">
        <label>
          API Key
          <span v-if="editingProvider" class="muted">
            · 已保存 {{ editingProvider.api_key }}（留空保留）
          </span>
        </label>
        <div class="row">
          <input
            v-model="form.api_key"
            :type="showKey ? 'text' : 'password'"
            :placeholder="editingProvider?.api_key || 'sk-...'"
            autocomplete="new-password"
          />
          <button type="button" class="ghost-btn" @click="showKey = !showKey">
            {{ showKey ? '隐藏' : '显示' }}
          </button>
        </div>
        <div v-if="editingProvider && revealed[editingProvider.id]" class="code-text" style="margin-top: 4px">
          已保存：{{ revealed[editingProvider.id] }}
        </div>
      </div>
      <div class="field">
        <label>extra（JSON：timeout / voice / protocol / temperature 等）</label>
        <textarea v-model="form.extraText" rows="4" spellcheck="false"></textarea>
      </div>
      <div class="row" style="gap: 16px">
        <label class="row tiny muted"><input v-model="form.enabled" type="checkbox" /> enabled</label>
        <label class="row tiny muted"><input v-model="form.is_default" type="checkbox" /> 设为该类型默认</label>
      </div>
    </section>

    <section v-for="kind in kinds" :key="kind.key" class="settings-section">
      <div class="row-between">
        <div>
          <h4>{{ kind.label }}</h4>
          <p class="settings-hint" style="margin-bottom: 0">{{ kind.hint }}</p>
        </div>
        <button type="button" class="ghost-btn" @click="startCreate(kind.key)">＋ 添加</button>
      </div>
      <div style="margin-top: 10px">
        <div v-for="provider in byKind(kind.key)" :key="provider.id" class="provider-card">
          <div class="provider-card-head">
            <span class="provider-kind">{{ provider.kind }}</span>
            <span class="provider-name">{{ provider.name }}</span>
            <span v-if="provider.is_default" class="badge ok">default</span>
            <span v-if="!provider.enabled" class="badge">已停用</span>
            <span v-if="provider.api_key_set" class="badge">key set</span>
            <div class="provider-actions">
              <button type="button" class="ghost-btn" @click="test(provider)">测试</button>
              <button type="button" class="ghost-btn" @click="startEdit(provider)">编辑</button>
              <button type="button" class="ghost-btn" @click="toggleEnabled(provider)">
                {{ provider.enabled ? '停用' : '启用' }}
              </button>
              <button
                v-if="!provider.is_default"
                type="button"
                class="ghost-btn"
                @click="makeDefault(provider)"
              >
                设默认
              </button>
              <button type="button" class="ghost-btn danger" @click="remove(provider)">删除</button>
            </div>
          </div>
          <div class="code-text">{{ provider.base_url }} · {{ provider.model }}</div>
          <div v-if="revealed[provider.id]" class="code-text" style="margin-top: 3px">
            key: {{ revealed[provider.id] }}
          </div>
        </div>
        <div v-if="!byKind(kind.key).length" class="empty-note">
          还没有 {{ kind.label }} 配置。点击「添加」，或先在 .env 填好 Key 重启后端。
        </div>
      </div>
    </section>
  </div>
</template>
