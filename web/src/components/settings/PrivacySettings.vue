<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { api } from '../../lib/api'
import { useSettingsStore } from '../../stores/settings'
import { useUiStore } from '../../stores/ui'

const settings = useSettingsStore()
const ui = useUiStore()

const form = reactive({
  retain_images: true,
  image_retention_days: 7,
  audio_retention_days: 7,
  reduced_motion: false,
  emotion_style: 'balanced',
})
const saving = ref(false)
const clearing = ref(false)

function fill() {
  const current = settings.settings
  if (!current) return
  form.retain_images = current.retain_images
  form.image_retention_days = current.image_retention_days
  form.audio_retention_days = current.audio_retention_days
  form.reduced_motion = current.reduced_motion
  form.emotion_style = current.emotion_style
}

watch(() => settings.settings, fill, { immediate: true, deep: true })

async function save() {
  saving.value = true
  try {
    await settings.save({
      retain_images: form.retain_images,
      image_retention_days: Math.max(1, Number(form.image_retention_days) || 7),
      audio_retention_days: Math.max(1, Number(form.audio_retention_days) || 7),
      reduced_motion: form.reduced_motion,
      emotion_style: form.emotion_style,
    })
  } finally {
    saving.value = false
  }
}

async function clearImages() {
  if (!window.confirm('清空所有抓帧图片与元数据？')) return
  clearing.value = true
  try {
    const result = await api.clearImages()
    ui.notify(`已清空 ${result.deleted} 张图片`, 'success')
  } catch (error) {
    ui.notify((error as Error).message, 'error')
  } finally {
    clearing.value = false
  }
}

onMounted(async () => {
  await settings.loadSettings()
  fill()
})
</script>

<template>
  <div>
    <section class="settings-section">
      <h4>数据留存</h4>
      <p class="settings-hint">
        所有数据都在本机 SQLite 与 media/ 目录。图片 / 音频只存文件路径；清理命令会先删文件再删记录。
      </p>
      <div class="check-row">
        <label><input v-model="form.retain_images" type="checkbox" /> 保留抓帧原图</label>
        <label><input v-model="form.reduced_motion" type="checkbox" /> 减少动画（prefers-reduced-motion）</label>
      </div>
      <div class="field-grid">
        <div class="field">
          <label>抓帧保留天数</label>
          <input v-model.number="form.image_retention_days" type="number" min="1" max="365" />
        </div>
        <div class="field">
          <label>TTS 音频保留天数</label>
          <input v-model.number="form.audio_retention_days" type="number" min="1" max="365" />
        </div>
      </div>
      <div class="field">
        <label>表情风格</label>
        <select v-model="form.emotion_style">
          <option value="balanced">平衡（推荐）</option>
          <option value="expressive">更外放</option>
          <option value="calm">更克制</option>
        </select>
      </div>
      <div class="settings-actions">
        <button type="button" class="ghost-btn danger" :disabled="clearing" @click="clearImages">
          {{ clearing ? '清理中…' : '清空所有抓帧' }}
        </button>
        <button type="button" class="paper-btn" :disabled="saving" @click="save">
          {{ saving ? '保存中…' : '保存隐私设置' }}
        </button>
      </div>
    </section>

    <section class="settings-section">
      <h4>本机路径</h4>
      <div class="code-card">
        <div class="code-line mono">SQLite: {{ settings.health?.db?.path || './db.sqlite3' }}</div>
        <div class="code-line mono">检查点: ./agent_checkpoints.sqlite3</div>
        <div class="code-line mono">媒体: ./media（images / tts）</div>
        <p class="settings-hint">
          备份：<span class="mono">sqlite3 db.sqlite3 ".backup 'backup/db.sqlite3'"</span>，检查点库同样要备份。
        </p>
      </div>
    </section>

    <section class="settings-section">
      <h4>长期记忆</h4>
      <p class="settings-hint">
        记忆的增删改、置顶和自动提取开关都在「长期记忆」页；所有内容只保存在本机数据库，不会上传。
      </p>
      <div class="settings-actions">
        <button type="button" class="ghost-btn" @click="ui.openSettings('memory')">前往记忆设置</button>
      </div>
    </section>
  </div>
</template>
