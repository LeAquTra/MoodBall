<script setup lang="ts">
import { commands } from '../commands'
import { useAssistant } from '../composables/useAssistant'

const { invoke } = useAssistant()
</script>

<template>
  <div class="cmd-grid">
    <button
      v-for="command in commands"
      :key="command.id"
      class="cmd-card"
      type="button"
      @click="invoke(command)"
    >
      <span class="cmd-top">
        <span class="mono dim">{{ command.no }}</span>
        <span class="cmd-run mono">RUN ↵</span>
      </span>
      <span class="cmd-title">{{ command.title }}</span>
      <span class="cmd-desc">{{ command.description }}</span>
      <span class="cmd-alias mono">{{ command.aliases.slice(0, 3).join(' · ') }}</span>
    </button>
  </div>
</template>
