<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ name: string; size?: number; stroke?: number }>(), {
  size: 16,
  stroke: 1.5,
})

/** 全部图标统一 24×24 视图框、线性描边；用路径数据描述，避免引入图标库。 */
const ICONS: Record<string, string[]> = {
  mic: ['M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z', 'M5 11a7 7 0 0 0 14 0', 'M12 18v3'],
  'mic-off': ['M4 4l16 16', 'M9 6a3 3 0 0 1 6 0v5', 'M15 15a3 3 0 0 1-6-1V9', 'M5 11a7 7 0 0 0 10.5 6', 'M19 11a7 7 0 0 1-1.5 4.3', 'M12 18v3'],
  camera: ['M3 8h3l2-3h8l2 3h3v11H3Z', 'M12 11a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7'],
  memory: ['M7 7h10v10H7Z', 'M9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4'],
  chat: ['M4 5h16v11H9l-5 4Z'],
  settings: [
    'M12 8.5a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7',
    'M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z',
  ],
  close: ['M6 6l12 12M18 6L6 18'],
  plus: ['M12 5v14M5 12h14'],
  'chevron-down': ['M6 9l6 6 6-6'],
  'chevron-right': ['M9 6l6 6-6 6'],
  search: ['M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14', 'M20 20l-3.6-3.6'],
  send: ['M12 19V5', 'M5 12l7-7 7 7'],
  pin: ['M9 4h6l-1 6 3 3H7l3-3-1-6Z', 'M12 13v7'],
  trash: ['M4 7h16', 'M9 7V4h6v3', 'M6 7l1 13h10l1-13', 'M10 11v5M14 11v5'],
  edit: ['M4 20h4L20 8l-4-4L4 16Z', 'M13 5l4 4'],
  eye: ['M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z', 'M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6'],
  volume: ['M4 9h4l5-4v14l-5-4H4Z', 'M16.5 8.5a5 5 0 0 1 0 7', 'M19 6a8 8 0 0 1 0 12'],
  spark: ['M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9Z'],
  refresh: ['M20 12a8 8 0 1 1-2.4-5.7', 'M20 4v5h-5'],
  check: ['M5 13l4 4L19 7'],
  stop: ['M7 7h10v10H7Z'],
  snapshot: ['M3 8h3l2-3h8l2 3h3v11H3Z', 'M12 11a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7', 'M18 5v3M16.5 6.5h3'],
  dot: ['M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6'],
}

const paths = computed(() => ICONS[props.name] ?? ICONS.dot)
</script>

<template>
  <svg
    class="icon"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="stroke"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <path v-for="(d, index) in paths" :key="index" :d="d" />
  </svg>
</template>

<style scoped>
.icon {
  display: block;
  flex: none;
}
</style>
