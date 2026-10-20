import { computed, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import type { Emotion } from '../lib/types'
import { useEmotionController, type EmotionSource } from '../composables/useEmotionController'

export interface BallApi {
  setEmotion: (id: string) => void
  handleAIMessage: (payload: unknown) => void
  setGaze?: (x: number, y: number) => void
  clearGaze?: () => void
  spin?: (turns?: number) => void
  burst?: (count?: number) => void
  bounce?: () => void
  resetIdle?: () => void
  setActive?: (active: boolean) => void
}

export interface EmotionHistoryEntry {
  id: string
  name: string
  source: EmotionSource
  at: number
}

const seed = (): Emotion[] =>
  ((globalThis as unknown as { EMOTION_SEED?: Emotion[] }).EMOTION_SEED ?? []).map((item) => ({
    id: item.id,
    name: item.name,
    group: item.group,
    desc: item.desc,
  }))

export const useBallStore = defineStore('ball', () => {
  const api = shallowRef<BallApi | null>(null)
  const current = ref('02')
  const tips = ref('')
  const lastSource = ref<EmotionSource>('state')
  const history = ref<EmotionHistoryEntry[]>([])
  const ready = ref(false)
  const emotions = ref<Emotion[]>(seed())
  let tipsTimer = 0

  const controller = useEmotionController({
    setEmotion: (id) => api.value?.setEmotion(id),
    onApplied: (id, source) => {
      current.value = id
      lastSource.value = source
      const emotion = emotions.value.find((item) => item.id === id)
      history.value.unshift({
        id,
        name: emotion?.name ?? id,
        source,
        at: Date.now(),
      })
      if (history.value.length > 30) history.value.length = 30
    },
  })

  const currentEmotion = computed(
    () => emotions.value.find((item) => item.id === current.value) ?? { id: current.value, name: current.value, group: 'agent' },
  )

  const groups = computed(() => {
    const map = new Map<string, Emotion[]>()
    for (const emotion of emotions.value) {
      const list = map.get(emotion.group) ?? []
      list.push(emotion)
      map.set(emotion.group, list)
    }
    return map
  })

  function setApi(next: BallApi | null) {
    api.value = next
    ready.value = Boolean(next)
    if (next) {
      next.setEmotion(current.value)
    }
  }

  function applyEmotion(id: string, source: EmotionSource = 'state', force = false): boolean {
    return controller.apply(id, source, force)
  }

  function setTips(text: string, ms = 4200) {
    tips.value = text
    if (tipsTimer) window.clearTimeout(tipsTimer)
    if (text) {
      tipsTimer = window.setTimeout(() => {
        tips.value = ''
        tipsTimer = 0
      }, ms)
    }
  }

  function handleAIMessage(payload: { emotionId?: string; tips?: string } | string) {
    let data: { emotionId?: string; tips?: string } = {}
    try {
      data = typeof payload === 'string' ? JSON.parse(payload) : payload
    } catch {
      return
    }
    if (data.emotionId) applyEmotion(data.emotionId, 'llm')
    if (data.tips) setTips(data.tips)
  }

  function pet() {
    applyEmotion('50', 'interaction', true)
    api.value?.burst?.(12)
    api.value?.bounce?.()
    setTips('被摸头了')
  }

  function reset(id = '02') {
    controller.reset(id)
    current.value = id
  }

  function dispose() {
    controller.dispose()
  }

  return {
    api,
    current,
    currentEmotion,
    tips,
    lastSource,
    history,
    ready,
    emotions,
    groups,
    setApi,
    applyEmotion,
    setTips,
    handleAIMessage,
    pet,
    reset,
    dispose,
  }
})
