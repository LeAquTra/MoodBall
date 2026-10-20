# AGENTS.md

> 面向后续 agent 的工程交接文档。**先读这一页，再动代码。**
> 项目：AROUSE —— 纯前端、离线语音唤起 Demo（Vue 3 + Vite + TS + Vosk WASM）。
> 最后核对：2026-10-18，`pnpm build` 通过，冒烟测试 `0 failed`。

---

## 0. 五句话理解项目

1. 用户说「小d小d」唤醒，再说一句指令（如「切换主题」），界面与 TTS 响应。
2. 识别**不走云**：Vosk 中文小模型（42MB tar.gz）在浏览器 WASM 里本地推理。
3. 识别失败才回退：**Vosk → Web Speech → 键盘模式**（`F2` 模拟唤醒 + 文本输入）。
4. 10 条纯前端指令，全部注册在 `src/commands.ts`，没有后端。
5. 视觉严格跟随 `DESIGN.md`（Linear 风格）：暗色、单一柠檬绿 `#e4f222`、12px 卡片、6px 按钮。

**改代码前必须知道的三个不变量**：
- 唤醒后必须重建 Vosk 识别器，否则唤醒词那句话会被当成指令执行。
- 所有异步流程必须校验 `session` 令牌，否则关麦后会被异步结果重新开麦。
- 只能使用 `F2` 模拟唤醒；`Ctrl+Shift+W` 在 Chromium 会关闭窗口。

---

## 1. 运行与验证

```bash
pnpm install
pnpm dev          # http://localhost:5173
pnpm build        # vue-tsc --noEmit && vite build
pnpm preview
```

| 事项 | 说明 |
| --- | --- |
| Node | ≥ 18（验证环境 24.15） |
| 包管理器 | pnpm ≥ 9（验证环境 11.7）；npm 也可 |
| 模型 | `public/models/model.tar.gz`（约 42MB，**不在 git 里**） |
| 模型重建 | 见 `public/models/README.md`，缺模型时 Vosk 会回退到 Web Speech |
| esbuild 构建 | `pnpm-workspace.yaml` 的 `allowBuilds.esbuild: true` 不能删，否则 `vite build` 失败 |

验证入口：

- 指令/唤醒词冒烟页：`http://localhost:5173/scripts/smoke.html`，期望最后一行 `total 0 failed`。
- 真实语音：点击麦克风 → 首次加载模型几秒 → 状态「聆听中」→ 说「小d小d」→ 说「切换主题」。
- 无麦克风/自动化：`F2` 模拟唤醒 → 输入「切换主题」→ 回车。

---

## 2. 项目地图

```
arouse_demo/
├─ AGENTS.md                     # 本文件（agent 入口）
├─ DESIGN.md                     # 视觉基线，改 UI 必读
├─ 语音唤起Demo开发文档.md        # 人类可读的开发文档
├─ 语音唤起可行性方案.md          # 选型/调研背景
├─ public/models/
│  ├─ model.tar.gz               # Vosk 中文模型（gitignored）
│  └─ README.md                  # 模型下载 + 打包命令
├─ scripts/smoke.html            # 指令/唤醒词自测页（仅 dev）
├─ src/
│  ├─ App.vue                    # 页面骨架、全局快捷键、Toast
│  ├─ style.css                  # 设计 token、布局、组件、动效
│  ├─ types.ts                   # VoiceState / CommandEffect / LogEntry
│  ├─ store.ts                   # 主题、播报、日志、Toast、面板
│  ├─ commands.ts                # 指令注册表 + 匹配算法
│  ├─ lib/text.ts                # normalize / Levenshtein / similarity
│  ├─ voice/
│  │  ├─ vosk.ts                 # 离线识别会话（主路径）
│  │  ├─ speech.ts               # Web Speech 回退 + TTS + 提示音
│  │  └─ wake.ts                 # 唤醒词正则 + Web Speech 监听（回退）
│  ├─ composables/useAssistant.ts# 状态机、引擎选择、会话令牌
│  └─ components/
│     ├─ TopBar.vue
│     ├─ VoiceConsole.vue
│     ├─ CommandGrid.vue
│     └─ SettingsDialog.vue
└─ docs/preview-{dark,light}.png # 预览图
```

依赖只有 `vue` 与 `vosk-browser`。**不要引入 Pinia、Vue Router、UI 组件库**——这个 Demo 刻意保持零额外抽象。

---

## 3. 运行时架构

### 3.1 数据流

```
麦克风
  ↓ getUserMedia → AudioContext(16k) → ScriptProcessor(4096)
Vosk KaldiRecognizer（WASM，本地）
  ↓ partialresult / result
detectWake()  ──命中──▶ 重建识别器 → command 阶段
  ↓ 未命中
下一句 final（8s 超时）
  ↓
matchCommand() → command.run() → speak()
  ↓
backToWake()
```

### 3.2 状态机

`VoiceState = idle | arming | armed | triggered | listening | thinking | speaking | error`

```
idle ──点麦克风──▶ arming ──模型+麦克风就绪──▶ armed
armed ──唤醒命中──▶ triggered ──220ms──▶ listening
listening ──final──▶ thinking ──180ms──▶ speaking ──TTS 结束──▶ armed
listening ──8s 超时──▶ armed
armed ──CMD-07 / 关闭──▶ idle
arming ──模型/权限失败──▶ Web Speech 或 keyboard
```

### 3.3 引擎选择（`useAssistant.arm()`）

| 顺序 | 条件 | `engine` | 行为 |
| --- | --- | --- | --- |
| 1 | Vosk 模型 + 16k AudioContext 可用 | `vosk` | 本地唤醒 + 本地指令 |
| 2 | Vosk 失败，且 `SpeechRecognition` 存在 | `webspeech` | 浏览器识别（可能 network 失败） |
| 3 | 以上都不可用 | `keyboard` | `F2` + 文本输入 |

权限被拒（`NotAllowedError` / `SecurityError`）或没有麦克风（`NotFoundError`）时**直接 error，不降级**——降级也拿不到音频。

---

## 4. 不变量（改代码前必读）

1. **唤醒后重建识别器**
   `VoskSession.handleWake()` 调 `scheduleRecognizerReset()`，用 `setTimeout(..., 0)`。
   禁止在 `recognizer.on('result')` 回调里同步 `remove()`；也禁止省略重建，否则「小弟 小弟」会被当指令。

2. **唤醒必须是叠词**
   正则是 `/小[弟滴迪低底地第丁d的]小[弟滴迪低底地第丁d的]/`。
   不要为了召回率加裸「小d」「小弟」——会大量误唤醒。

3. **16k 是硬约束**
   `new AudioContext({ sampleRate: 16000 })` 后必须检查 `context.sampleRate === 16000`；
   不等就抛 `SAMPLE_RATE_*` 走回退。**不要**把 48k 音频直接喂给 16k 模型。

4. **ScriptProcessor 要接到 destination**
   必须经 0 增益 `GainNode` 连接 `destination`，否则 `onaudioprocess` 不触发。

5. **播报时静音识别**
   `respond()` 里 `vosk.setMuted(true)` → `await speak()` → `setMuted(false)`。
   漏掉会把 TTS 播报声识别成新指令（自唤醒/自执行）。

6. **会话令牌**
   `arm()` / `disarm()` / `dispose()` 都会 `session += 1`。
   任何 `await` 之后都要 `if (token !== session) return`。新增异步流程同样处理。

7. **`busy` 串行化**
   `execute()` / `invoke()` 用 `busy` 防重入；`execute` 的 `force` 参数只给 Vosk 命令回调使用。

8. **指令匹配阈值 0.66、同分取长别名**
   改阈值或打分公式必须同步更新 `scripts/smoke.html` 的歧义用例（「关闭语音」vs「关闭语音播报」）。

9. **快捷键只用 `F2`**
   `Ctrl+Shift+W` 是 Chromium 的关闭窗口，无法 `preventDefault`。不要改回去。

10. **单一强调色**
    柠檬绿 `--accent` 只用于麦克风球；不要再给按钮/卡片加第二种彩色。

---

## 5. 核心契约

### 5.1 指令

```ts
interface CommandDef {
  id: string            // 'theme.toggle'
  no: string            // 'CMD-01'
  title: string
  description: string
  aliases: string[]     // 含 ASR 常见误写
  run: () => CommandResult
}

interface CommandResult {
  reply: string
  effects?: CommandEffect[]   // 'stop-voice' | 'focus-input' | 'scroll-commands' | 'scroll-top'
}
```

`run()` 直接改 Vue 状态（`theme` / `panels` / `logs`），返回给 TTS 的文本。**不要在 `run()` 里做异步 I/O。**

### 5.2 `useAssistant()` 导出

| 名称 | 类型 | 用途 |
| --- | --- | --- |
| `state` | `Ref<VoiceState>` | 状态机 |
| `engine` | `Ref<'vosk' \| 'webspeech' \| 'keyboard'>` | 当前引擎 |
| `mode` | `Ref<'voice' \| 'keyboard'>` | 简化模式 |
| `stateText` / `stateCode` | `ComputedRef<string>` | 中文/等宽状态 |
| `lastUserText` | `Ref<string>` | 最近识别文本 |
| `focusSignal` | `Ref<number>` | 自增触发输入框聚焦 |
| `arm` | `() => Promise<void>` | 开麦（异步，含模型加载） |
| `disarm` / `toggle` | `() => void` | 关麦 / 开关切换 |
| `simulateWake` | `() => void` | `F2` 用 |
| `execute` | `(text, token?, force?) => Promise<void>` | 文本指令入口 |
| `invoke` | `(command) => Promise<void>` | 点击卡片执行 |
| `focusInput` / `dispose` | `() => void` | 聚焦 / 卸载清理 |

### 5.3 Store

`src/store.ts` 导出：`theme`、`ttsEnabled`、`panels`、`logs`、`toast`、`pushLog`、`clearLogs`、`toggleTheme`、`notify`。
主题优先级：URL `?theme=` > `localStorage` > `dark`。

---

## 6. 常见任务配方

### 6.1 新增一条指令

1. `src/commands.ts` 的 `commands` 数组追加一项。
2. 需要新交互时，在 `types.ts` 的 `CommandEffect` 加值，并在 `useAssistant.applyEffects()` 处理。
3. `scripts/smoke.html` 加一条用例。

```ts
{
  id: 'panel.close',
  no: 'CMD-11',
  title: '关闭面板',
  description: '收起当前打开的弹层',
  aliases: ['关闭面板', '收起设置', '关掉弹层'],
  run: () => {
    panels.settings = false
    return { reply: '面板已收起。' }
  },
}
```

注意：`id` 必须唯一；`no` 递增；`aliases` 要覆盖同音/俗称；返回的 `reply` 会被 TTS 读出来。

### 6.2 改唤醒词

只改 `src/voice/wake.ts`：

```ts
const WAKE_CHARS = '弟滴迪低底地第丁d的'
const WAKE_PATTERN = new RegExp(`小[${WAKE_CHARS}]小[${WAKE_CHARS}]`)
```

换词（例如「小助小助」）需要同时改字符集与 `WAKE_GREETINGS`，并在 smoke 页加真实 Vosk 输出用例。
**不要**引入拼音库，除非同时评估包体积（当前策略是字符集 + 正则）。

### 6.3 换 ASR 引擎

保持 `useAssistant.execute(text)` 这个入口不变，二选一：

- **本地**：实现一个与 `VoskSession` 同形的类（`start(callbacks)` / `stop()` / `dispose()` / `setMuted()` / `backToWake()`），在 `arm()` 的 `startVosk()` 位置替换。
- **云端**：替换 `speech.ts` 的 `listenOnce()`，签名保持 `Promise<string>`；token 必须由后端签发，不能把 AK/SK 放前端。

### 6.4 改视觉

只改 `src/style.css` 的 token 与组件类，不要改结构去凑样式。
改完同时看暗/亮两套：`http://localhost:5173/?theme=light`。
麦克风球仍是全页唯一实心柠檬绿。

---

## 7. 设计系统（硬规则）

| 规则 | 值 |
| --- | --- |
| 画布 / 卡片 | `#08090a` / `#0f1011` |
| 边框 | 卡片用 `inset 0 0 0 1px #23252a`；分隔线/导航用 1px `border` |
| 强调色 | `#e4f222`，仅麦克风球 |
| 卡片 / 按钮 / 胶囊圆角 | `12px` / `6px` / `9999px` |
| 区块间距 | `96px`；元素间距 `8px` |
| 内容宽度 | `1200px` |
| 字体 | Inter 回退栈 + JetBrains Mono 回退栈，不加载 Web Font |
| 字重 | 不超过 590 |
| 标题行高 | 中文 `1.06`（DESIGN 的 `1` 只适用于拉丁字母） |

禁止：渐变按钮、彩色正文、16px+ 卡片圆角、投影堆叠、第二种强调色。

---

## 8. 测试与验收

### 8.1 必跑

```bash
pnpm build   # 必须 0 error；当前产物：主包 101.8KB + vosk chunk 5.79MB + CSS 16.7KB
```

### 8.2 冒烟页

`http://localhost:5173/scripts/smoke.html`

期望覆盖：
- 指令命中：`切换主题`、`切换 主题`（Vosk 带空格）、`关闭语音播报`、`关闭语音`、`打开设置`、`清空记录`、`回到顶部`、`你是谁`。
- 歧义：`关闭语音播报` → `tts.toggle`，`关闭语音` → `voice.stop`。
- 负例：`今天天气怎么样`、`切换` 均不命中。
- 唤醒：`小d小d`、`小滴小滴`、`小弟 小弟`、`小丁 小的` 命中；`你好`、`今天天气不错` 不命中。
- remainder：`小弟 小弟 切换 主题` → `切换主题`。

最后一行必须是 `total 0 failed`。

### 8.3 端到端（可选）

真实麦克风：点麦克风 → 允许 → 等「聆听中」→ 说「小d小d」→ 说「切换主题」。

无麦克风自动化：Chromium 加 `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream`，
点击 `.orb` 后轮询 `.state-text`，应到「聆听中」，日志出现「离线语音已就绪」。

### 8.4 验收线

- 首次加载模型 ≤ 10s（本地）。
- 唤醒 → UI 反馈 ≤ 500ms。
- 安静 1m 唤醒率 ≥ 90%，误唤醒 ≤ 1 次/小时（small 模型现实值）。
- 关闭语音、卸载组件后麦克风指示灯熄灭。

---

## 9. 已知坑（按踩坑概率排序）

1. **模型 404**：`public/models/model.tar.gz` 缺失或不是 tar.gz。按 `public/models/README.md` 生成，不要用官方 zip 直接改名。
2. **`vosk-browser` 静态 import**：会把 5.8MB 打进主包。必须保持 `await import('vosk-browser')`。
3. **唤醒词被当指令**：漏了重建识别器，或重建用了同步 `remove()`。
4. **TTS 自唤醒**：漏了 `setMuted`，或播报结束后立刻恢复监听没有缓冲。
5. **关麦后又自己开麦**：`await` 后没校验 `session`。
6. **48k 音频喂 16k 模型**：`AudioContext({ sampleRate: 16000 })` 被浏览器忽略时没抛错。
7. **脚本处理器不触发**：忘了 0 增益 `GainNode` 接 `destination`。
8. **打包失败 `esbuild`**：删了 `pnpm-workspace.yaml` 的 `allowBuilds`。
9. **快捷键冲突**：把 `F2` 改回 `Ctrl+Shift+W`。
10. **主题闪烁**：在 `main.ts` 里手写 `data-theme` 而不是走 `store` 的 `watch(theme, { immediate: true })`。

---

## 10. 边界（不要做）

- 不要声称「完全离线」却保留 Web Speech 主路径——当前主路径是 Vosk，回退才联网。
- 不要用 UA 判断 Edge 能力；用 `speechSupported` + 实际错误。
- 不要给 Demo 加路由、登录、后端、状态管理库；这是单页演示。
- 不要把 42MB 模型提交进 git（`.gitignore` 已忽略）。
- 不要在没有麦克风的环境里断言语音功能「坏了」；先用 `F2` 验证指令链路。

---

## 11. 文档索引

| 文档 | 用途 |
| --- | --- |
| `AGENTS.md` | agent 入口：约束、契约、配方、验收 |
| `语音唤起Demo开发文档.md` | 人类开发文档：设计映射、架构、实现细节、扩展 |
| `语音唤起可行性方案.md` | 选型背景：Web Speech / Porcupine / sherpa / Edge 评估 |
| `DESIGN.md` | 视觉基线，改 UI 前必读 |
| `public/models/README.md` | 42MB 模型的获取与打包 |

如文档与代码冲突，**以 `src/` 为准**，并顺手修正文档。
