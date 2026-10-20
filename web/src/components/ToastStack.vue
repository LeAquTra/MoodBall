<script setup lang="ts">
import { useUiStore } from '../stores/ui'

const ui = useUiStore()
</script>

<template>
  <div class="toast-stack" aria-live="polite">
    <div v-for="toast in ui.toasts" :key="toast.id" class="toast" :class="toast.kind">
      <span class="toast-dot" aria-hidden="true"></span>
      <span class="toast-text">{{ toast.message }}</span>
      <button type="button" aria-label="关闭提示" @click="ui.dismiss(toast.id)">×</button>
    </div>
  </div>
</template>
