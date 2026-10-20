<script setup lang="ts">
import { computed, onMounted } from 'vue'
import Icon from '../../components/Icon.vue'
import { useMemoryStore } from '../../stores/memory'
import { useSettingsStore } from '../../stores/settings'
import { useUiStore } from '../../stores/ui'

const memory = useMemoryStore()
const settings = useSettingsStore()
const ui = useUiStore()

onMounted(() => {
  void memory.load()
})

const caps = computed(() => [
  { label: '全部记忆', value: memory.stats.total, hint: `上限 ${memory.settings.max_items}` },
  { label: '置顶', value: memory.stats.pinned, hint: '每轮都会进 prompt' },
  { label: '7 天内用过', value: memory.stats.used_7d, hint: `本轮召回上限 ${memory.settings.recall_limit}` },
  { label: '自动提取', value: memory.stats.auto, hint: '来源 auto' },
])

async function toggleAuto() {
  await settings.save({ memory_auto_extract: !memory.settings.auto_extract })
  await memory.load({ silent: true })
}

async function toggleEnabled() {
  await settings.save({ memory_enabled: !memory.settings.enabled })
  await memory.load({ silent: true })
}

async function saveLimit(event: Event) {
  const value = Number((event.target as HTMLInputElement).value)
  if (!Number.isFinite(value)) return
  await settings.save({ memory_max_items: Math.max(10, Math.min(5000, Math.round(value))) })
  await memory.load({ silent: true })
}

function openDrawer() {
  ui.settingsOpen = false
  ui.memoryOpen = true
  void memory.load()
}
</script>

<template>
  <div>
    <section class="settings-section">
      <div class="stat-grid">
        <div v-for="cap in caps" :key="cap.label" class="stat-card">
          <span class="stat-value mono">{{ cap.value }}</span>
          <span class="stat-label">{{ cap.label }}</span>
          <span class="stat-hint">{{ cap.hint }}</span>
        </div>
      </div>
    </section>

    <section class="settings-section">
      <h4>记忆开关</h4>
      <p class="settings-hint">
        记忆是「一句话事实」：用户偏好、长期习惯、明确要求记住的事情。它和聊天记录分开存储，可以逐条编辑、置顶或删除。
      </p>
      <div class="setting-row">
        <div class="setting-row-text">
          <strong>启用长期记忆</strong>
          <span>关闭后 Agent 不再召回或写入记忆；已有数据保留，仍可在记忆抽屉里手动管理。</span>
        </div>
        <button
          type="button"
          class="switch"
          :class="{ on: memory.settings.enabled }"
          role="switch"
          :aria-checked="memory.settings.enabled"
          @click="toggleEnabled"
        ></button>
      </div>
      <div class="setting-row">
        <div class="setting-row-text">
          <strong>自动提取</strong>
          <span>每轮对话后额外调用一次对话模型，提取 0-3 条事实。默认关闭，开启后会产生额外 token 消耗。</span>
        </div>
        <button
          type="button"
          class="switch"
          :class="{ on: memory.settings.auto_extract }"
          role="switch"
          :aria-checked="memory.settings.auto_extract"
          @click="toggleAuto"
        ></button>
      </div>
      <div class="setting-row">
        <div class="setting-row-text">
          <strong>容量上限</strong>
          <span>超出后自动淘汰最久未使用的未置顶记忆。范围 10–5000。</span>
        </div>
        <input
          class="number-input"
          type="number"
          min="10"
          max="5000"
          :value="memory.settings.max_items"
          @change="saveLimit"
        />
      </div>
    </section>

    <section class="settings-section">
      <h4>使用方式</h4>
      <div class="memory-usage">
        <div class="usage-row">
          <Icon name="chat" :size="15" />
          <div>
            <strong>「记住：我每天早上喝美式」</strong>
            <span>Agent 调用 remember_fact，写入一条对话来源的记忆。</span>
          </div>
        </div>
        <div class="usage-row">
          <Icon name="search" :size="15" />
          <div>
            <strong>「你还记得我喜欢喝什么吗？」</strong>
            <span>路由到记忆节点，召回相关事实并累计使用次数。</span>
          </div>
        </div>
        <div class="usage-row">
          <Icon name="pin" :size="15" />
          <div>
            <strong>置顶</strong>
            <span>置顶记忆每轮都会进入上下文，适合姓名、称呼、长期偏好。</span>
          </div>
        </div>
      </div>
      <div class="settings-actions">
        <button type="button" class="ghost-btn" @click="openDrawer">打开记忆管理</button>
        <button type="button" class="paper-btn" @click="memory.load()">刷新统计</button>
      </div>
    </section>
  </div>
</template>
