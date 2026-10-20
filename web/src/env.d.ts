/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}

interface Window {
  EmotionBall?: {
    create: (el: HTMLElement, opts?: Record<string, unknown>) => EmotionBallInstance
    config?: unknown
  }
  EMOTION_SEED?: EmotionSeed[]
  EMOTION_GROUPS?: EmotionGroup[]
  webkitAudioContext?: typeof AudioContext
}

interface EmotionSeed {
  id: string
  name: string
  group: string
  desc?: string
  en?: { name?: string; desc?: string }
}

interface EmotionGroup {
  key: string
  name: string
  en?: string
}

interface EmotionBallInstance {
  setEmotion: (id: string) => void
  handleAIMessage: (payload: unknown) => void
  setGaze?: (x: number, y: number) => void
  clearGaze?: () => void
  spin?: (turns?: number) => void
  burst?: (count?: number) => void
  bounce?: () => void
  resetIdle?: () => void
  setActive?: (active: boolean) => void
  renderStatic?: () => void
  startTour?: (ids: string[], ms: number) => void
  stopTour?: () => void
  on?: (name: string, cb: (payload: unknown) => void) => void
  destroy?: () => void
}
