<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Icon from './Icon.vue'
import { useCameraStore } from '../stores/camera'
import { useChatStore } from '../stores/chat'
import { useUiStore } from '../stores/ui'

const camera = useCameraStore()
const chat = useChatStore()
const ui = useUiStore()
const previewFailed = ref(false)

const previewAvailable = computed(() => camera.enabled && camera.opencv)
const snapshotUrl = computed(() => {
  const url = camera.snapshotInfo?.url
  return typeof url === 'string' ? url : ''
})

watch(
  () => camera.previewKey,
  () => {
    previewFailed.value = false
  },
)

onMounted(async () => {
  if (!camera.previewOn) await camera.startPreview()
  await camera.loadImages(chat.currentId ?? undefined)
})

onBeforeUnmount(() => {
  void camera.stopPreview()
})

async function takeSnapshot() {
  await camera.snapshot(chat.currentId ?? undefined)
}

function close() {
  ui.cameraOpen = false
  void camera.stopPreview()
}

async function clearImages() {
  if (!window.confirm('清空所有抓帧图片与元数据？')) return
  await camera.clearImages()
}
</script>

<template>
  <div class="drawer-layer" @click.self="close">
    <aside class="drawer drawer-camera" role="dialog" aria-modal="false" aria-label="摄像头">
      <header class="drawer-head">
        <div class="drawer-title">
          <h2>摄像头</h2>
          <span class="drawer-sub">
            {{ camera.opencv ? (camera.opened ? '已打开' : '待机') : 'OpenCV 不可用' }} ·
            {{ camera.width || '—' }} × {{ camera.height || '—' }}
          </span>
        </div>
        <div class="drawer-actions">
          <button type="button" class="icon-btn" title="刷新" aria-label="刷新摄像头" @click="camera.refresh()">
            <Icon name="refresh" />
          </button>
          <button type="button" class="icon-btn" title="关闭" aria-label="关闭摄像头面板" @click="close">
            <Icon name="close" />
          </button>
        </div>
      </header>

      <div class="drawer-body">
        <div class="camera-preview">
          <img
            v-if="previewAvailable && camera.previewOn && !previewFailed"
            :src="camera.previewUrl"
            alt="摄像头实时预览"
            @error="previewFailed = true"
          />
          <div v-else class="preview-placeholder">
            <template v-if="!camera.opencv">未检测到 OpenCV。<br />安装 opencv-python 后重启后端。</template>
            <template v-else-if="!camera.enabled">摄像头已在配置中关闭（CAMERA_ENABLED=0）。</template>
            <template v-else-if="previewFailed">
              预览没有出来，可能是摄像头被占用或权限被拒。<br />点刷新或释放后重试。
            </template>
            <template v-else>正在打开摄像头…</template>
          </div>
        </div>

        <div v-if="camera.lastError" class="inline-error">{{ camera.lastError }}</div>

        <div class="camera-meta">
          <span><i class="meta-key">状态</i>{{ camera.opened ? '已打开' : '待机' }}</span>
          <span><i class="meta-key">预览</i>{{ camera.previewOn ? 'MJPEG' : '关闭' }}</span>
          <span><i class="meta-key">会话</i>{{ chat.currentId ? chat.currentId.slice(0, 8) : '未开始' }}</span>
          <span><i class="meta-key">留存</i>7 天</span>
        </div>

        <div class="camera-actions">
          <button type="button" class="paper-btn" :disabled="camera.loading" @click="takeSnapshot">
            <Icon name="snapshot" :size="14" />
            {{ camera.loading ? '抓取中…' : '抓一帧' }}
          </button>
          <button type="button" class="ghost-btn" @click="camera.refresh()">刷新</button>
          <button type="button" class="ghost-btn" @click="camera.stopPreview()">释放摄像头</button>
          <button type="button" class="ghost-btn danger" @click="clearImages">清空图片</button>
        </div>

        <div v-if="snapshotUrl" class="last-snapshot">
          <img :src="snapshotUrl" alt="最近抓帧" />
          <div class="snapshot-info">
            <strong>最近抓帧已落盘</strong>
            <span class="mono">{{ snapshotUrl }}</span>
          </div>
        </div>

        <div class="section-label">
          <span>历史抓帧</span>
          <span class="mono">{{ camera.images.length }}</span>
        </div>
        <div v-if="camera.images.length" class="image-grid">
          <a
            v-for="image in camera.images"
            :key="image.id"
            :href="image.url"
            target="_blank"
            rel="noreferrer"
            :title="image.created_at"
          >
            <img :src="image.url" alt="历史抓帧" loading="lazy" />
          </a>
        </div>
        <div v-else class="memory-empty">还没有抓帧。点「抓一帧」，或让小球看一眼。</div>

        <p class="drawer-note">
          个人本机模式：摄像头由后端独占，页面关闭或点「释放」后句柄才会释放；不会自动上传任何图片。
        </p>
      </div>
    </aside>
  </div>
</template>
