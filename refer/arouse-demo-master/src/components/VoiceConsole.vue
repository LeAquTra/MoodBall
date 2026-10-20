<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useAssistant } from '../composables/useAssistant'
import { logs, notify, ttsEnabled } from '../store'
import type { LogRole, VoiceState } from '../types'

const { state, stateText, stateCode, toggle, execute, simulateWake, focusSignal } = useAssistant()

const draft = ref('')
const inputEl = ref<HTMLInputElement | null>(null)

const HINTS: Record<VoiceState, string> = {
  idle: '点击麦克风开启语音，或直接输入指令',
  arming: '正在加载离线模型…',
  armed: '说「小d小d」唤醒，或按 F2 模拟',
  triggered: '我在听，请说指令',
  listening: '正在识别…',
  thinking: '正在处理…',
  speaking: '正在播报…',
  error: '语音不可用，请检查权限或改用文字',
}

const ROLE_LABEL: Record<LogRole, string> = {
  user: 'YOU',
  assistant: 'AROUSE',
  system: 'SYS',
}

const hint = computed(() => HINTS[state.value])
const recent = computed(() => logs.value.slice(-5))
const placeholder = computed(() =>
  state.value === 'triggered' ? '例如：切换主题' : '输入指令，例如：切换主题',
)

watch(focusSignal, async () => {
  await nextTick()
  inputEl.value?.focus()
})

function submit() {
  const text = draft.value
  draft.value = ''
  void execute(text)
}

function toggleTts() {
  ttsEnabled.value = !ttsEnabled.value
  notify(ttsEnabled.value ? '语音播报已开启' : '语音播报已关闭')
}
</script>

<template>
  <section class="console card" aria-label="语音控制台">
    <header class="console-head">
      <div class="state-line">
        <span class="state-dot" :data-state="state" />
        <span class="state-text">{{ stateText }}</span>
      </div>
      <span class="mono dim">{{ stateCode }}</span>
    </header>

    <div class="orb-stage" :data-state="state">
      <span class="orb-ring" />
      <span class="orb-ring orb-ring--inner" />

      <button
        class="orb"
        type="button"
        :aria-label="state === 'idle' || state === 'error' ? '开启语音' : '关闭语音'"
        @click="toggle"
      >
        <svg v-if="state === 'thinking'" class="orb-icon orb-icon--spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 3a9 9 0 1 1-6.4 2.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
        </svg>
        <svg v-else-if="state === 'speaking'" class="orb-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M4 9.5h3.2L13 5v14l-5.8-4.5H4z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" />
          <path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8 8 0 0 1 0 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
        </svg>
        <svg v-else-if="state === 'error'" class="orb-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 8v5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
          <circle cx="12" cy="16.5" r="1" fill="currentColor" />
          <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.5" />
        </svg>
        <svg v-else class="orb-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect x="9" y="3" width="6" height="11" rx="3" stroke="currentColor" stroke-width="1.6" />
          <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
        </svg>
      </button>

      <div class="orb-bars" aria-hidden="true">
        <i v-for="index in 5" :key="index" :style="{ animationDelay: `${(index - 1) * 90}ms` }" />
      </div>
    </div>

    <p class="console-hint">{{ hint }}</p>

    <ol class="log" aria-live="polite">
      <li v-for="entry in recent" :key="entry.id" :data-role="entry.role">
        <span class="log-meta mono">{{ ROLE_LABEL[entry.role] }}</span>
        <span class="log-text">{{ entry.text }}</span>
      </li>
    </ol>

    <form class="composer" @submit.prevent="submit">
      <input
        ref="inputEl"
        v-model="draft"
        type="text"
        autocomplete="off"
        spellcheck="false"
        :placeholder="placeholder"
        aria-label="输入指令"
      />
      <button class="btn-ghost" type="submit">执行</button>
    </form>

    <footer class="console-foot mono">
      <button class="link-btn" type="button" @click="simulateWake">模拟唤醒</button>
      <span class="dim">F2</span>
      <button class="link-btn" type="button" @click="toggleTts">
        {{ ttsEnabled ? '播报 ON' : '播报 OFF' }}
      </button>
    </footer>
  </section>
</template>
