import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../lib/api'
import { streamSSE } from '../lib/sse'
import type { ChatHandlers, Conversation, MemoryItem, Message, ToolEvent } from '../lib/types'
import { useBallStore } from './ball'
import { useMemoryStore } from './memory'
import { useUiStore } from './ui'

const now = () => new Date().toISOString()
const tempId = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`

export interface SendOptions {
  speak?: boolean
  withVision?: boolean
  handlers?: ChatHandlers
}

export const useChatStore = defineStore('chat', () => {
  const ui = useUiStore()
  const ball = useBallStore()
  const memory = useMemoryStore()

  const conversations = ref<Conversation[]>([])
  const currentId = ref<string | null>(null)
  const messages = ref<Message[]>([])
  const streaming = ref(false)
  const loadingMessages = ref(false)
  const error = ref<string | null>(null)
  const status = ref<'idle' | 'thinking' | 'acting' | 'speaking'>('idle')
  const draft = ref('')
  const visionMode = ref(false)
  let controller: AbortController | null = null

  const currentConversation = computed(
    () => conversations.value.find((item) => item.id === currentId.value) ?? null,
  )

  function findMessage(id: string): Message | undefined {
    return messages.value.find((message) => message.id === id || message.client_id === id)
  }

  function patchMessage(id: string, patch: Partial<Message>) {
    const index = messages.value.findIndex((message) => message.id === id)
    if (index >= 0) messages.value[index] = { ...messages.value[index], ...patch }
  }

  async function loadConversations(selectLatest = false) {
    try {
      const result = await api.conversations()
      conversations.value = result.items
      if (selectLatest && !currentId.value && result.items.length) {
        await selectConversation(result.items[0].id)
      }
    } catch (err) {
      ui.notify((err as Error).message, 'error')
    }
  }

  async function createConversation(title = ''): Promise<Conversation | null> {
    try {
      const result = await api.createConversation(title)
      conversations.value = [result.conversation, ...conversations.value]
      currentId.value = result.conversation.id
      messages.value = []
      return result.conversation
    } catch (err) {
      ui.notify((err as Error).message, 'error')
      return null
    }
  }

  async function selectConversation(id: string) {
    if (streaming.value) stop()
    currentId.value = id
    loadingMessages.value = true
    try {
      const result = await api.messages(id)
      messages.value = result.items.map(normalizeMessage)
    } catch (err) {
      ui.notify((err as Error).message, 'error')
    } finally {
      loadingMessages.value = false
    }
  }

  async function newConversation() {
    await createConversation()
  }

  async function deleteConversation(id: string) {
    try {
      await api.deleteConversation(id)
      conversations.value = conversations.value.filter((item) => item.id !== id)
      if (currentId.value === id) {
        currentId.value = null
        messages.value = []
        if (conversations.value.length) await selectConversation(conversations.value[0].id)
      }
      ui.notify('会话已删除', 'success')
    } catch (err) {
      ui.notify((err as Error).message, 'error')
    }
  }

  async function ensureConversation(text: string): Promise<string | null> {
    if (currentId.value) return currentId.value
    const conversation = await createConversation(text.slice(0, 24))
    return conversation?.id ?? null
  }

  async function sendMessage(text: string, options: SendOptions = {}): Promise<boolean> {
    const content = text.trim()
    if (!content || streaming.value) return false
    const conversationId = await ensureConversation(content)
    if (!conversationId) return false

    error.value = null
    streaming.value = true
    status.value = 'thinking'
    memory.noteRecalled([])
    ball.applyEmotion('30', 'state')

    const userTempId = tempId('user')
    const assistantTempId = tempId('assistant')
    messages.value.push({
      id: userTempId,
      client_id: userTempId,
      conversation_id: conversationId,
      role: 'user',
      content,
      created_at: now(),
      pending: true,
    })
    messages.value.push({
      id: assistantTempId,
      client_id: assistantTempId,
      conversation_id: conversationId,
      role: 'assistant',
      content: '',
      created_at: now(),
      pending: true,
      tool_events: [],
    })

    controller = new AbortController()
    const handlers = options.handlers ?? {}

    try {
      await streamSSE(
        '/api/chat/stream/',
        {
          conversation_id: conversationId,
          text: content,
          with_vision: Boolean(options.withVision ?? visionMode.value),
          speak: options.speak ?? true,
        },
        {
          signal: controller.signal,
          onEvent: (event) => {
            const data = event.data as Record<string, unknown>
            switch (event.event) {
              case 'meta': {
                handlers.onMeta?.(data)
                break
              }
              case 'state': {
                const value = String(data.state ?? '')
                if (value === 'thinking') status.value = 'thinking'
                else if (value === 'acting') status.value = 'acting'
                else if (value === 'speaking') status.value = 'speaking'
                else if (value === 'done') status.value = 'idle'
                const emotionId = data.emotion ? String(data.emotion) : ''
                if (emotionId && ['thinking', 'acting', 'speaking'].includes(value)) {
                  ball.applyEmotion(emotionId, 'state')
                }
                handlers.onState?.({ state: value, node: String(data.node ?? ''), emotion: emotionId })
                break
              }
              case 'token': {
                const delta = String(data.text ?? '')
                const message = findMessage(assistantTempId)
                if (message) message.content += delta
                handlers.onToken?.(delta)
                break
              }
              case 'emotion': {
                const emotionId = String(data.emotionId ?? '')
                const tips = data.tips ? String(data.tips) : ''
                if (emotionId) {
                  patchMessage(assistantTempId, { emotion_id: emotionId })
                  // 后端 plan_emotion 已经完成仲裁与 ID 校验，这里作为最终规则强制落地；
                  // 若仍按 llm 提案处理，会被 speaking(39) 的状态锁丢弃。
                  ball.applyEmotion(emotionId, 'rule', true)
                }
                if (tips) ball.setTips(tips)
                handlers.onEmotion?.({
                  emotionId,
                  intensity: Number(data.intensity ?? 0.5),
                  tips,
                  source: String(data.source ?? 'rule'),
                })
                break
              }
              case 'tool': {
                const tool = data as unknown as ToolEvent
                const message = findMessage(assistantTempId)
                if (message) {
                  message.tool_events = [...(message.tool_events ?? []), tool]
                }
                handlers.onTool?.(tool)
                break
              }
              case 'memory': {
                const list = Array.isArray(data.items) ? (data.items as MemoryItem[]) : []
                if (list.length) {
                  memory.noteRecalled(list)
                  ball.setTips(`翻到 ${list.length} 条记忆`)
                }
                handlers.onMemory?.({
                  items: list,
                  count: Number(data.count ?? list.length),
                  query: String(data.query ?? ''),
                })
                break
              }
              case 'audio': {
                const url = String(data.url ?? '')
                if (url) handlers.onAudio?.(url, Number(data.duration_ms ?? 0))
                break
              }
              case 'warning': {
                const message = String(data.message ?? '')
                if (message) ui.notify(message, 'warning')
                handlers.onWarning?.(message)
                break
              }
              case 'error': {
                const message = String(data.message ?? '对话失败')
                error.value = message
                ui.notify(message, 'error')
                handlers.onError?.({ code: String(data.code ?? 'ERROR'), message })
                break
              }
              case 'done': {
                const reply = String(data.reply ?? '')
                const message = findMessage(assistantTempId)
                if (message && !message.content.trim() && reply) message.content = reply
                patchMessage(assistantTempId, {
                  id: String(data.message_id ?? assistantTempId),
                  emotion_id: String(data.emotionId ?? message?.emotion_id ?? ''),
                  pending: false,
                  latency_ms: Number(data.latency_ms ?? 0),
                  tokens_in: Number((data.usage as Record<string, unknown> | undefined)?.in ?? 0),
                  tokens_out: Number((data.usage as Record<string, unknown> | undefined)?.out ?? 0),
                  tool_events: (data.tool_events as ToolEvent[] | undefined) ?? message?.tool_events ?? [],
                })
                status.value = 'idle'
                handlers.onDone?.(data)
                void loadConversations()
                if (memory.autoExtraction) {
                  window.setTimeout(() => void memory.load({ silent: true }), 1600)
                }
                break
              }
            }
          },
        },
      )
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        const message = (err as Error).message || '流式对话失败'
        error.value = message
        const assistant = findMessage(assistantTempId)
        if (assistant && !assistant.content) assistant.content = '这一轮没有成功，请重试。'
        ui.notify(message, 'error')
        handlers.onError?.({ code: 'STREAM_FAILED', message })
      }
    } finally {
      const assistant = findMessage(assistantTempId)
      if (assistant) assistant.pending = false
      const user = findMessage(userTempId)
      if (user) user.pending = false
      streaming.value = false
      status.value = 'idle'
      controller = null
    }
    return true
  }

  function stop() {
    controller?.abort()
    controller = null
    streaming.value = false
    status.value = 'idle'
    ball.applyEmotion('41', 'state', true)
    window.setTimeout(() => ball.applyEmotion('02', 'state', true), 900)
  }

  function reset() {
    stop()
    currentId.value = null
    messages.value = []
    error.value = null
  }

  return {
    conversations,
    currentId,
    currentConversation,
    messages,
    streaming,
    loadingMessages,
    error,
    status,
    draft,
    visionMode,
    loadConversations,
    createConversation,
    selectConversation,
    newConversation,
    deleteConversation,
    sendMessage,
    stop,
    reset,
  }
})

function normalizeMessage(message: Message): Message {
  return {
    ...message,
    client_id: message.client_id ?? message.id,
    tool_events: (message.meta?.tool_events as ToolEvent[] | undefined) ?? [],
  }
}
