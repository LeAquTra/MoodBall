import { ref } from 'vue'

export type EmotionSource = 'state' | 'rule' | 'llm' | 'interaction'

const PRIORITY: Record<EmotionSource, number> = {
  llm: 1,
  interaction: 2,
  rule: 3,
  state: 4,
}

const STATE_LOCKED = new Set(['30', '32', '35', '39', '40', '34', '38'])
const MIN_HOLD_MS = 900
const DEBOUNCE_MS = 600

const VALID_IDS = new Set<string>(
  ((globalThis as unknown as { EMOTION_SEED?: { id: string }[] }).EMOTION_SEED ?? []).map((item) => item.id),
)

export interface EmotionControllerOptions {
  setEmotion: (id: string) => void
  onApplied?: (id: string, source: EmotionSource) => void
  onRejected?: (id: string, reason: string) => void
}

export function useEmotionController(options: EmotionControllerOptions) {
  const current = ref('02')
  let lastAt = 0
  let pending: { id: string; source: EmotionSource; at: number } | null = null
  let timer: number | undefined

  function clearPending() {
    pending = null
    if (timer !== undefined) {
      window.clearTimeout(timer)
      timer = undefined
    }
  }

  function commit(id: string, source: EmotionSource) {
    pending = null
    if (timer !== undefined) {
      window.clearTimeout(timer)
      timer = undefined
    }
    current.value = id
    lastAt = performance.now()
    options.setEmotion(id)
    options.onApplied?.(id, source)
  }

  function apply(id: string, source: EmotionSource = 'state', force = false): boolean {
    if (!VALID_IDS.has(id)) {
      console.warn('[ball] invalid emotion id', id)
      options.onRejected?.(id, 'invalid')
      return false
    }
    if (source === 'llm' && STATE_LOCKED.has(current.value)) {
      options.onRejected?.(id, 'state-locked')
      return false
    }
    const now = performance.now()
    if (id === current.value) {
      clearPending()
      return false
    }
    const holdLeft = MIN_HOLD_MS - (now - lastAt)
    if (!force && holdLeft > 0 && PRIORITY[source] < PRIORITY.state) {
      if (!pending || now - pending.at > DEBOUNCE_MS) {
        pending = { id, source, at: now }
        if (timer !== undefined) window.clearTimeout(timer)
        timer = window.setTimeout(() => {
          const next = pending
          pending = null
          timer = undefined
          if (next) commit(next.id, next.source)
        }, holdLeft)
      }
      return true
    }
    commit(id, source)
    return true
  }

  function reset(id = '02') {
    clearPending()
    current.value = id
    lastAt = 0
    options.setEmotion(id)
    options.onApplied?.(id, 'state')
  }

  function dispose() {
    clearPending()
  }

  return { current, apply, reset, dispose, validIds: VALID_IDS }
}
