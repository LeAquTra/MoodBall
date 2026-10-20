<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { api } from '../../lib/api'
import { playAudio, unlockAudio } from '../../audio/ttsPlayer'
import { useSettingsStore } from '../../stores/settings'
import { useUiStore } from '../../stores/ui'

const settings = useSettingsStore()
const ui = useUiStore()

const form = reactive({
  wake_word: '小d小d',
  wakeVariantsText: '',
  wake_confirm_hits: 2,
  wake_cooldown_ms: 1500,
  command_timeout_ms: 8000,
  tts_voice: 'Cherry',
  tts_model: 'qwen3-tts-flash',
  tts_enabled: true,
  speak_replies: true,
})
const saving = ref(false)
const previewing = ref(false)
const previewText = ref('你好，我是 MoodBall。今天也一起待着吧。')
const voiceStatus = ref<{ asr: { ok: boolean; message?: string; model?: string; cuda?: boolean }; enabled: boolean } | null>(null)

function fill() {
  const current = settings.settings
  if (!current) return
  form.wake_word = current.wake_word
  form.wakeVariantsText = (current.wake_variants ?? []).join(', ')
  form.wake_confirm_hits = current.wake_confirm_hits
  form.wake_cooldown_ms = current.wake_cooldown_ms
  form.command_timeout_ms = current.command_timeout_ms
  form.tts_voice = current.tts_voice
  form.tts_model = current.tts_model
  form.tts_enabled = current.tts_enabled
  form.speak_replies = current.speak_replies
}

watch(() => settings.settings, fill, { immediate: true, deep: true })

async function save() {
  saving.value = true
  try {
    await settings.save({
      wake_word: form.wake_word.trim() || '小d小d',
      wake_variants: form.wakeVariantsText
        .split(/[,，\n]/)
        .map((item) => item.trim())
        .filter(Boolean),
      wake_confirm_hits: Math.max(1, Math.min(5, Number(form.wake_confirm_hits) || 2)),
      wake_cooldown_ms: Math.max(0, Number(form.wake_cooldown_ms) || 0),
      command_timeout_ms: Math.max(1000, Number(form.command_timeout_ms) || 8000),
      tts_voice: form.tts_voice.trim() || 'Cherry',
      tts_model: form.tts_model.trim() || 'qwen3-tts-flash',
      tts_enabled: form.tts_enabled,
      speak_replies: form.speak_replies,
    })
    await refreshVoiceStatus()
  } finally {
    saving.value = false
  }
}

async function refreshVoiceStatus() {
  try {
    voiceStatus.value = await api.voiceStatus()
  } catch {
    voiceStatus.value = null
  }
}

async function previewTts() {
  previewing.value = true
  try {
    await unlockAudio()
    const result = await api.ttsPreview(previewText.value, form.tts_voice)
    await playAudio(result.audio_url)
    ui.notify(`已合成 · ${result.duration_ms} ms`, 'success')
  } catch (error) {
    ui.notify((error as Error).message, 'error')
  } finally {
    previewing.value = false
  }
}

onMounted(async () => {
  await settings.loadSettings()
  fill()
  await refreshVoiceStatus()
})
</script>

<template>
  <div>
    <section class="settings-section">
      <h4>唤醒</h4>
      <p class="settings-hint">
        不做独立 KWS：用 ASR 的 partial 文本做正则匹配。默认叠词「小d小d」，同音字符集（弟 / 滴 / 迪 / 丁 / 的…）会自动命中。
        修改后下一次语音会话生效。
      </p>
      <div class="field-grid">
        <div class="field">
          <label>唤醒词</label>
          <input v-model="form.wake_word" />
        </div>
        <div class="field">
          <label>二次确认次数（1–5）</label>
          <input v-model.number="form.wake_confirm_hits" type="number" min="1" max="5" />
        </div>
      </div>
      <div class="field">
        <label>同音变体（逗号分隔）</label>
        <input v-model="form.wakeVariantsText" placeholder="你好小d, 嗨小d, 你好小滴" />
      </div>
      <div class="field-grid">
        <div class="field">
          <label>唤醒冷却（ms）</label>
          <input v-model.number="form.wake_cooldown_ms" type="number" min="0" step="100" />
        </div>
        <div class="field">
          <label>指令超时（ms）</label>
          <input v-model.number="form.command_timeout_ms" type="number" min="1000" step="500" />
        </div>
      </div>
    </section>

    <section class="settings-section">
      <h4>语音合成</h4>
      <p class="settings-hint">
        默认走百炼 Qwen3-TTS。播报期间会静音上行并在结束后冷却 300 ms，减少自唤醒；失败时只显示文字。
      </p>
      <div class="field-grid">
        <div class="field">
          <label>音色</label>
          <input v-model="form.tts_voice" placeholder="Cherry / Ethan / longanyang" />
        </div>
        <div class="field">
          <label>模型</label>
          <input v-model="form.tts_model" placeholder="qwen3-tts-flash" />
        </div>
      </div>
      <div class="row" style="gap: 18px; margin-bottom: 10px">
        <label class="row tiny muted"><input v-model="form.tts_enabled" type="checkbox" /> 启用 TTS</label>
        <label class="row tiny muted"><input v-model="form.speak_replies" type="checkbox" /> 自动播报回复</label>
      </div>
      <div class="field">
        <label>试听文本</label>
        <div class="row">
          <input v-model="previewText" style="flex: 1" />
          <button type="button" class="ghost-btn" :disabled="previewing" @click="previewTts">
            {{ previewing ? '合成中…' : '试听' }}
          </button>
        </div>
      </div>
      <div class="row" style="justify-content: flex-end; margin-top: 6px">
        <button type="button" class="paper-btn" :disabled="saving" @click="save">
          {{ saving ? '保存中…' : '保存语音设置' }}
        </button>
      </div>
    </section>

    <section class="settings-section">
      <div class="row-between">
        <h4>ASR 服务状态</h4>
        <button type="button" class="ghost-btn" @click="refreshVoiceStatus">刷新</button>
      </div>
      <div class="provider-card">
        <div class="row" style="flex-wrap: wrap">
          <span class="status-dot" :class="voiceStatus?.asr?.ok ? 'ok' : 'bad'"></span>
          <strong style="font-size: 12.5px">{{ voiceStatus?.asr?.ok ? '已连接' : '未连接' }}</strong>
          <span v-if="voiceStatus?.asr?.model" class="muted tiny">{{ voiceStatus.asr.model }}</span>
          <span v-if="voiceStatus?.asr?.cuda" class="badge ok">CUDA</span>
          <span v-if="voiceStatus?.asr?.message" class="badge bad">{{ voiceStatus.asr.message }}</span>
        </div>
        <p class="settings-hint" style="margin: 8px 0 0">
          启动命令：<span class="mono">.\.venv-asr\Scripts\uvicorn asr_service.app:app --host 127.0.0.1 --port 9100</span>。
          没有 GPU 或模型未就绪时，用「按住说话」或文字输入即可。
        </p>
      </div>
    </section>
  </div>
</template>
