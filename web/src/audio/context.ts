const AudioContextClass =
  window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext

let sharedContext: AudioContext | null = null

export function getAudioContext(): AudioContext | null {
  if (!AudioContextClass) return null
  if (!sharedContext || sharedContext.state === 'closed') {
    sharedContext = new AudioContextClass({ latencyHint: 'interactive' })
  }
  return sharedContext
}

export async function unlockAudio(): Promise<AudioContext | null> {
  const ctx = getAudioContext()
  if (!ctx) return null
  if (ctx.state === 'suspended') {
    try {
      await ctx.resume()
    } catch {
      /* 用户手势之外无法恢复 */
    }
  }
  return ctx
}

export function audioSupported(): boolean {
  return Boolean(AudioContextClass)
}
