import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../lib/api'
import type { McpServer, ToolEntry } from '../lib/types'
import { useUiStore } from './ui'

export const useToolsStore = defineStore('tools', () => {
  const ui = useUiStore()
  const tools = ref<ToolEntry[]>([])
  const servers = ref<McpServer[]>([])
  const loading = ref(false)
  const refreshing = ref(false)
  const lastError = ref('')

  async function loadTools() {
    try {
      const result = await api.tools()
      tools.value = result.items
      lastError.value = result.last_error
    } catch (err) {
      lastError.value = (err as Error).message
    }
  }

  async function loadServers() {
    try {
      const result = await api.mcpServers()
      servers.value = result.items
    } catch (err) {
      ui.notify((err as Error).message, 'error')
    }
  }

  async function loadAll() {
    loading.value = true
    await Promise.allSettled([loadTools(), loadServers()])
    loading.value = false
  }

  async function refreshTools() {
    refreshing.value = true
    try {
      const result = await api.refreshTools()
      tools.value = result.items
      lastError.value = result.last_error
      await loadServers()
      ui.notify(`工具已刷新 · ${result.items.length} 个`, 'success')
    } catch (err) {
      ui.notify((err as Error).message, 'error')
    } finally {
      refreshing.value = false
    }
  }

  async function createServer(payload: Record<string, unknown>) {
    try {
      const result = await api.createMcpServer(payload)
      servers.value.push(result.server)
      ui.notify('MCP server 已添加', 'success')
      await loadTools()
      return result.server
    } catch (err) {
      ui.notify((err as Error).message, 'error')
      return null
    }
  }

  async function updateServer(id: string, payload: Record<string, unknown>) {
    try {
      const result = await api.updateMcpServer(id, payload)
      const index = servers.value.findIndex((item) => item.id === id)
      if (index >= 0) servers.value[index] = result.server
      ui.notify('MCP server 已更新', 'success')
      await loadTools()
      return result.server
    } catch (err) {
      ui.notify((err as Error).message, 'error')
      return null
    }
  }

  async function deleteServer(id: string) {
    try {
      await api.deleteMcpServer(id)
      servers.value = servers.value.filter((item) => item.id !== id)
      ui.notify('MCP server 已删除', 'success')
      await loadTools()
    } catch (err) {
      ui.notify((err as Error).message, 'error')
    }
  }

  async function testServer(id: string) {
    try {
      const result = await api.testMcpServer(id)
      ui.notify(`发现 ${result.tool_count} 个工具 · ${result.latency_ms} ms`, 'success')
      await loadServers()
      return result
    } catch (err) {
      ui.notify((err as Error).message, 'error')
      return null
    }
  }

  async function refreshServer(id: string) {
    try {
      const result = await api.refreshMcpServer(id)
      ui.notify(`已刷新 ${result.tool_count} 个工具`, 'success')
      await Promise.allSettled([loadServers(), loadTools()])
      return result
    } catch (err) {
      ui.notify((err as Error).message, 'error')
      return null
    }
  }

  async function toggleTool(name: string, enabled: boolean) {
    try {
      await api.toggleTool(name, enabled)
      await loadTools()
      ui.notify(enabled ? '工具已启用' : '工具已禁用', 'success')
    } catch (err) {
      ui.notify((err as Error).message, 'error')
    }
  }

  async function invokeTool(name: string, args: Record<string, unknown>) {
    try {
      const result = await api.invokeTool(name, args)
      if (result.status === 'ok') ui.notify(`执行成功 · ${result.duration_ms} ms`, 'success')
      else ui.notify(result.error || '工具执行失败', 'error')
      return result
    } catch (err) {
      ui.notify((err as Error).message, 'error')
      return null
    }
  }

  return {
    tools,
    servers,
    loading,
    refreshing,
    lastError,
    loadTools,
    loadServers,
    loadAll,
    refreshTools,
    createServer,
    updateServer,
    deleteServer,
    testServer,
    refreshServer,
    toggleTool,
    invokeTool,
  }
})
