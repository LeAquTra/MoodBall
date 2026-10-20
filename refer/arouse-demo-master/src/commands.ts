import { normalize, similarity } from './lib/text'
import { clearLogs, panels, theme, toggleTheme, ttsEnabled } from './store'
import type { CommandEffect } from './types'

export interface CommandResult {
  reply: string
  effects?: CommandEffect[]
}

export interface CommandDef {
  id: string
  no: string
  title: string
  description: string
  aliases: string[]
  run: () => CommandResult
}

export const commands: CommandDef[] = [
  {
    id: 'theme.toggle',
    no: 'CMD-01',
    title: '切换主题',
    description: '在午夜与日光两套配色之间切换',
    aliases: ['切换主题', '换个主题', '换主题', '切换外观', '切换风格', '主题切换'],
    run: () => {
      const next = toggleTheme()
      return { reply: next === 'dark' ? '已切换到午夜主题。' : '已切换到日光主题。' }
    },
  },
  {
    id: 'theme.dark',
    no: 'CMD-02',
    title: '午夜模式',
    description: '回到默认的深色界面',
    aliases: ['午夜模式', '深色模式', '暗色模式', '夜间模式', '深色主题', '黑色主题'],
    run: () => {
      theme.value = 'dark'
      return { reply: '已切换到午夜主题。' }
    },
  },
  {
    id: 'theme.light',
    no: 'CMD-03',
    title: '日光模式',
    description: '切换到浅色界面',
    aliases: ['日光模式', '浅色模式', '亮色模式', '日间模式', '浅色主题', '白色主题'],
    run: () => {
      theme.value = 'light'
      return { reply: '已切换到日光主题。' }
    },
  },
  {
    id: 'settings.open',
    no: 'CMD-04',
    title: '打开设置',
    description: '查看主题、播报与引擎信息',
    aliases: ['打开设置', '设置', '偏好设置', '配置', '打开偏好'],
    run: () => {
      panels.settings = true
      return { reply: '设置面板已打开。' }
    },
  },
  {
    id: 'commands.list',
    no: 'CMD-05',
    title: '指令列表',
    description: '展开全部可用指令',
    aliases: ['指令列表', '帮助', '你会什么', '能做什么', '有什么指令', '列出指令', '指令'],
    run: () => ({
      reply: `现在一共 ${commands.length} 条指令，已经帮你滚动到列表。`,
      effects: ['scroll-commands'],
    }),
  },
  {
    id: 'logs.clear',
    no: 'CMD-06',
    title: '清空记录',
    description: '清空控制台里的对话',
    aliases: ['清空记录', '清空对话', '清除记录', '清屏', '清空控制台'],
    run: () => {
      clearLogs()
      return { reply: '记录已清空。' }
    },
  },
  {
    id: 'voice.stop',
    no: 'CMD-07',
    title: '停止聆听',
    description: '关闭麦克风并退出语音模式',
    aliases: ['停止聆听', '关闭语音', '别听了', '退出语音', '关闭麦克风', '停止监听'],
    run: () => ({
      reply: '好的，麦克风已经关闭。',
      effects: ['stop-voice'],
    }),
  },
  {
    id: 'tts.toggle',
    no: 'CMD-08',
    title: '语音播报',
    description: '打开或关闭语音回复',
    aliases: ['语音播报', '关闭语音播报', '开启语音播报', '打开播报', '关闭播报', '静音', '取消静音'],
    run: () => {
      ttsEnabled.value = !ttsEnabled.value
      return { reply: ttsEnabled.value ? '语音播报已开启。' : '语音播报已关闭。' }
    },
  },
  {
    id: 'page.top',
    no: 'CMD-09',
    title: '回到顶部',
    description: '把页面滚回最上方',
    aliases: ['回到顶部', '滚动到顶部', '回到上面', '回顶部'],
    run: () => ({
      reply: '已经回到页面顶部。',
      effects: ['scroll-top'],
    }),
  },
  {
    id: 'about',
    no: 'CMD-10',
    title: '你是谁',
    description: '介绍一下这个 Demo',
    aliases: ['你是谁', '介绍一下自己', '你叫什么', '你是什么', '自我介绍'],
    run: () => ({
      reply:
        '我是 AROUSE，一个纯前端的语音唤起 Demo。说「小d小d」唤醒我，然后用一句指令切换主题、清空记录，或者打开设置。',
    }),
  },
]

export interface CommandMatch {
  command: CommandDef
  alias: string
  score: number
}

const MIN_SCORE = 0.66

export function matchCommand(input: string): CommandMatch | null {
  const text = normalize(input)
  if (!text) return null

  let best: CommandMatch | null = null

  for (const command of commands) {
    for (const alias of command.aliases) {
      const key = normalize(alias)
      if (!key) continue

      let score: number
      if (text === key) {
        score = 1
      } else if (text.includes(key)) {
        score = 0.8 + 0.18 * (key.length / text.length)
      } else if (key.includes(text) && text.length >= Math.max(2, key.length * 0.6)) {
        score = 0.7
      } else {
        score = similarity(text, key) * 0.9
      }

      if (!best || score > best.score || (score === best.score && key.length > normalize(best.alias).length)) {
        best = { command, alias, score }
      }
    }
  }

  return best && best.score >= MIN_SCORE ? best : null
}
