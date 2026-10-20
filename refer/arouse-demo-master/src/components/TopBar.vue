<script setup lang="ts">
import { computed } from 'vue'
import { panels, theme } from '../store'
import { useAssistant } from '../composables/useAssistant'

const { state } = useAssistant()

const live = computed(() =>
  ['armed', 'triggered', 'listening', 'thinking', 'speaking'].includes(state.value),
)

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
}
</script>

<template>
  <header class="nav">
    <div class="nav-inner">
      <a class="brand" href="#top" aria-label="AROUSE 首页">
        <svg class="brand-mark" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M12 2v20M2 12h20M4.9 4.9l14.2 14.2M19.1 4.9L4.9 19.1"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
          />
        </svg>
        <span class="brand-name">AROUSE</span>
        <span class="brand-sub mono">voice console</span>
      </a>

      <nav class="nav-links" aria-label="主导航">
        <a class="nav-link" href="#commands">指令</a>
        <a class="nav-link" href="#about">机制</a>

        <span class="live-pill mono" :data-live="live">
          <span class="live-dot" />
          {{ live ? 'LIVE' : 'STANDBY' }}
        </span>

        <button class="icon-btn" type="button" :aria-label="theme === 'dark' ? '切换到日光模式' : '切换到午夜模式'" @click="toggleTheme">
          <svg v-if="theme === 'dark'" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="4.2" stroke="currentColor" stroke-width="1.5" />
            <path
              d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.2 5.2l1.6 1.6M17.2 17.2l1.6 1.6M18.8 5.2l-1.6 1.6M6.8 17.2l-1.6 1.6"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
            />
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M20 14.5A8.2 8.2 0 0 1 9.5 4a8.4 8.4 0 1 0 10.5 10.5Z"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linejoin="round"
            />
          </svg>
        </button>

        <button class="btn-ghost" type="button" @click="panels.settings = true">设置</button>
      </nav>
    </div>
  </header>
</template>
