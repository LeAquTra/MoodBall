<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import type { BallApi } from '../stores/ball'
import { useBallStore } from '../stores/ball'

const props = withDefaults(
  defineProps<{
    emotion?: string
    shape?: 'blob' | 'wedge' | 'gem'
    lite?: boolean
  }>(),
  { emotion: '02', shape: 'blob', lite: false },
)

const emit = defineEmits<{
  (event: 'ready'): void
  (event: 'change', id: string): void
  (event: 'error', payload: unknown): void
}>()

const ballStore = useBallStore()
const host = ref<HTMLDivElement | null>(null)
const instance = shallowRef<EmotionBallInstance | null>(null)
const currentEmotion = computed(() => ballStore.current)

onMounted(() => {
  if (!host.value) return
  const sdk = window.EmotionBall
  if (!sdk?.create) {
    emit('error', { message: 'EmotionBall SDK 未加载' })
    return
  }
  const ball = sdk.create(host.value, {
    emotion: props.emotion,
    shape: props.shape,
    lite: props.lite,
    idle: false,
    autostart: true,
    color: '#F3F0EA',
    eyeColor: '#1A1A1A',
    label: 'MoodBall 表情小球',
  })
  instance.value = ball
  ball.on?.('change', (payload: unknown) => {
    const id = (payload as { id?: string })?.id
    if (id) emit('change', id)
  })
  ball.on?.('error', (payload: unknown) => emit('error', payload))

  const api: BallApi = {
    setEmotion: (id: string) => ball.setEmotion(id),
    handleAIMessage: (payload: unknown) => ball.handleAIMessage(payload),
    setGaze: (x: number, y: number) => ball.setGaze?.(x, y),
    clearGaze: () => ball.clearGaze?.(),
    spin: (turns?: number) => ball.spin?.(turns),
    burst: (count?: number) => ball.burst?.(count),
    bounce: () => ball.bounce?.(),
    resetIdle: () => ball.resetIdle?.(),
    setActive: (active: boolean) => ball.setActive?.(active),
  }
  ballStore.setApi(api)
  emit('ready')
})

watch(
  () => ballStore.current,
  (id) => instance.value?.setEmotion(id),
)

onBeforeUnmount(() => {
  ballStore.setApi(null)
  try {
    instance.value?.stopTour?.()
    instance.value?.destroy?.()
  } catch {
    /* ignore */
  }
  instance.value = null
})

defineExpose({
  setEmotion(id: string) {
    instance.value?.setEmotion(id)
  },
  handleAIMessage(payload: unknown) {
    instance.value?.handleAIMessage(payload)
  },
})
</script>

<template>
  <div
    ref="host"
    class="ball-host"
    data-testid="emotion-ball"
    :data-emotion="currentEmotion"
    role="img"
    aria-label="MoodBall 表情小球"
  />
</template>
