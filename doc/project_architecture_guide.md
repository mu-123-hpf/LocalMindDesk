# LocalMindDesk — 保姆级项目架构讲解

> 📌 **读者对象**：完全不了解本项目的人也能看懂
> 📌 **写作时间**：2026-05-02

---

## 📦 项目一句话总结

**LocalMindDesk 是一个"本地 AI 桌面助手"**。

它连接本地运行的 AI 模型（通过 LM Studio），让你在一个漂亮的界面里跟 AI 对话，
并且 AI 可以帮你**操作电脑**（创建文件、运行程序、截图、搜索代码等），而不只是回答问题。

---

## 🏗️ 整体架构（先看大图）

```
┌─────────────────────────────────────────────────────────┐
│                    用户看到的界面                         │
│              frontend/ (HTML + CSS + JS)                 │
│          ↕ HTTP 请求 (localhost:8000)                     │
│                  后端 API 服务                            │
│              app/main.py (FastAPI)                       │
│                      │                                   │
│        ┌─────────────┼─────────────┐                     │
│        ↓             ↓             ↓                     │
│   意图路由      记忆系统      工具系统                     │
│  agent_router  memory.py   tools/                       │
│        │             │             │                     │
│        ↓             ↓             ↓                     │
│   本地 AI 模型    SQLite 数据库    操作系统                │
│  (LM Studio)   (LocalMindDesk.db)  (文件/进程)               │
│                                                         │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─               │
│  Electron 桌面壳（把网页变成桌面应用）                      │
│              electron/main.js                            │
└─────────────────────────────────────────────────────────┘
```

**关键理解**：这是一个 **前后端分离** 的应用：
- **前端** = 用户看到的界面（HTML/CSS/JS），跑在浏览器/Electron 里
- **后端** = Python 服务，处理所有逻辑（对话、文件操作、记忆等）
- **两者通过 HTTP API 通信**（前端 fetch → 后端 FastAPI）

---

## 📁 顶层目录结构

```
localminddesk lm/
├── app/                 ← 🧠 后端核心代码（Python）
├── frontend/            ← 🎨 前端界面（HTML/CSS/JS）
├── electron/            ← 🖥️ 桌面应用壳（Electron）
├── doc/                 ← 📝 所有文档/进展记录
├── .agents/             ← 🤖 Agent 人格 prompt 文件
├── assets/              ← 🖼️ 应用图标等资源
├── data/                ← 💾 运行时数据（数据库/截图等）
├── build/               ← 📦 打包相关配置
├── config.json          ← ⚙️ 全局配置文件
├── requirements.txt     ← 📋 Python 依赖清单
├── package.json         ← 📋 Electron/Node 依赖清单
└── test_integration.py  ← 🧪 集成测试
```

---

## 🧠 app/ — 后端核心（最重要的目录）

这是整个项目的**大脑**，所有智能逻辑都在这里。

### 🚪 app/main.py — 后端入口（API 服务器）

**为什么需要这个文件？**
前端想跟后端通信，需要一个"接口"。`main.py` 就是所有接口的集合。

**它做什么？**
```python
# 用 FastAPI 框架创建一个 HTTP 服务器
app = FastAPI()

# 定义各种 API 接口：
@app.post("/api/chat")          # 用户发消息 → 这里处理
@app.get("/api/health")         # 前端检查后端是否活着
@app.post("/api/actions/execute") # 执行操作（创建文件等）
@app.get("/api/workspace/tree")  # 获取文件夹结构
@app.get("/api/sessions")       # 获取会话列表
# ... 还有很多
```

**比喻**：`main.py` 就像一个**前台接待员**，用户的所有请求先到这里，
然后它分配给不同的部门（模块）去处理。

---

### 🔀 app/agent_router.py — 意图路由引擎（调度中心）

**为什么需要这个文件？**
用户说的话可能是各种意图：聊天、操作文件、搜索、做 PPT...
需要一个"调度中心"来判断用户想干什么，然后分配给不同的 Agent 处理。

**核心函数 `route()`**：
```python
def route(user_message, history, system_prompt, workspace_path):
    # 1. 思维引擎：检测对话模式（执行/协作/审查）
    # 2. 压缩过长对话
    # 3. 构建增强版 system prompt
    # 4. 分析用户意图：config? action? tool? chat?
    # 5. 并行调度对应的 Agent
    # 6. 合并结果返回给前端
```

**比喻**：`agent_router` 就像一个**部门经理**。
前台把客户带来，经理判断"这个客户是要改配置、要操作文件、还是纯聊天"，
然后同时派不同的人去处理。

---

### 🧠 app/thinking_engine.py — 批判性思维引擎（★新）

**为什么需要这个文件？**
让 AI 不再是"你说什么我就做什么"的工具人，而是有自己思考的搭档。

**三大功能**：

1. **对话模式检测**：
   ```python
   detect_mode("创建文件 test.py")       → "execute"（直接做）
   detect_mode("我想加个用户系统")        → "collaborate"（先讨论）
   detect_mode("帮我看看这段代码")        → "review"（深度分析）
   ```

2. **反问触发器**：
   ```python
   check_clarification_needed("加个功能")
   → "[反问提示] 用户需求较模糊，先确认细节再行动"
   ```

3. **项目感知扫描**：
   ```python
   scan_project_context("/path/to/your/project")
   → "[项目上下文] 文件数: 50, 技术栈: Python(25), JS(10), TODO: 3处"
   ```

---

### 🤖 app/llm_provider.py — AI 模型调用层

**为什么需要这个文件？**
项目需要调用 AI 模型来生成回复。这个文件封装了"跟 AI 模型通信"的逻辑。

**它做什么？**
```python
def chat(messages, system_prompt, temperature, max_tokens):
    # 把消息发送给 LM Studio 的 API（http://127.0.0.1:1234/v1）
    # LM Studio 在本地运行 Gemma 4 模型
    # 收到回复后返回文本
```

**比喻**：`llm_provider` 就像一个**翻译官**。
项目内部的请求格式 → 转换成 LM Studio 能理解的格式 → 发送 → 收到回复 → 转换回来。

---

### 🎯 app/action_planner.py — 操作规划器

**为什么需要这个文件？**
当用户说"帮我截个图放到文件夹"时，需要有人**理解**这句话并**拆解**成具体操作步骤。

**核心逻辑（正则匹配）**：
```python
def plan_actions(user_message):
    # "截图" → [{"tool": "screen_capture", "params": {...}}]
    # "运行 python test.py" → [{"tool": "shell_exec", "params": {"command": "python test.py"}}]
    # "创建 hello.txt" → [{"tool": "file_op", "params": {"action": "write", ...}}]
    # "发给微信 xxx" → [{"tool": "wechat_send", "params": {...}}]
```

**为什么用正则而不是让 AI 来分析？**
因为正则匹配**快**（毫秒级），而让 AI 分析需要几秒。
对于明确的操作指令，正则足够准确。

---

### ⚙️ app/action_engine.py — 操作执行引擎

**为什么需要这个文件？**
`action_planner` 规划好了"做什么"，但还需要有人**真正去做**。
`action_engine` 就是执行者，同时也是**安全守门员**。

**两大职责**：
1. **安全门**（SafetyGate）：判断操作是否危险
   ```python
   SafetyGate.assess("shell_exec", {"command": "rm -rf /"})
   → {"blocked": True, "reason": "危险命令"}
   ```
2. **执行委托**：调用具体的工具去执行
   ```python
   execute_action("file_op", {"action": "write", "path": "test.txt", "content": "hello"})
   → {"success": True, "message": "文件已创建"}
   ```

---

### 🔧 app/tools/ — 工具集合（真正干活的人）

这个目录里每个文件就是一个"工具"：

| 文件 | 工具名 | 干什么 |
|------|--------|--------|
| `shell_tool.py` | shell_exec | 执行终端命令（如 `python test.py`） |
| `file_tool.py` | file_op | 文件操作（创建/读取/删除/复制/移动） |
| `gui_tool.py` | gui_action / screen_capture | GUI 自动化 + 截图 |
| `search_tool.py` | code_search | 在代码中搜索（类似 grep） |
| `web_search.py` | search | 联网搜索 |
| `ppt_maker.py` | make_ppt | 自动生成 PPT |
| `doc_maker.py` | make_doc | 自动生成 Word 文档 |
| `wechat_tool.py` | wechat_send | 微信发消息/文件 |
| `registry.py` | — | 工具注册中心（管理所有工具） |
| `base.py` | — | 工具基类（所有工具的模板） |

**`base.py` 为什么重要？**
它定义了所有工具必须实现的"接口"：
```python
class BaseTool:
    def name(self): ...          # 工具名称
    def description(self): ...   # 工具描述
    def danger_level(self): ...  # 危险等级
    def execute(self, params):.. # 真正执行的方法
```
这样所有工具都有统一的调用方式。

**`registry.py` 为什么重要？**
它是工具的"电话簿"——所有工具都注册在这里：
```python
registry.register(ShellTool())    # 注册终端工具
registry.register(FileTool())     # 注册文件工具
registry.execute("shell_exec", {"command": "dir"})  # 按名字调用
```

---

### 💾 app/memory.py — 会话记忆（数据库层）

**为什么需要？** AI 需要记住你之前说过什么。

**功能**：
- 创建/列出/删除对话会话
- 保存/加载每个会话的消息历史
- 使用 SQLite 数据库存储（`data/LocalMindDesk.db`）

---

### 🧬 app/vector_memory.py — 向量记忆（长期记忆）

**为什么需要？** 普通记忆只记住当前会话。向量记忆可以跨会话搜索相关信息。

**原理**：把文本转成数学向量，用余弦相似度搜索最相关的历史记忆。

---

### 📝 app/memory_extractor.py — 记忆提取器

**为什么需要？** 聊天结束后，自动从对话中提取"值得记住的东西"存入长期记忆。

---

### 🗜️ app/compact.py — 对话压缩器

**为什么需要？** AI 模型有上下文窗口限制。对话太长时，自动把旧消息压缩成摘要。

```python
# 原始: 100 条消息 (50000 tokens)
# 压缩后: [摘要] + 最近 6 条消息 (3000 tokens)
```

---

### 🎭 app/agent_profile.py — Agent 人格管理

**为什么需要？** 用户可以自定义 AI 的名字、图标、说话风格。

```json
// data/agent_profile.json
{
  "identity": {"name": "LocalMindDesk", "icon": "🧠", "role": "AI 搭档"},
  "behavior": {"response_style": "balanced", "response_length": "medium"},
  "ui_preferences": {"theme": "hacker"}
}
```

---

### 🔄 app/meta_agent.py — 自进化 Agent

**为什么需要？** 用户说"你以后叫小助手"或"回答简洁一点"时，AI 能**自动调整自己的配置**。

---

### 📋 app/config.py — 配置管理

**为什么需要？** 集中管理所有配置（模型地址、温度、端口等）。

```python
class AppConfig:
    active_model = "local-lmstudio"
    temperature = 0.7
    max_tokens = 131072
    server_port = 8000
```

---

### 🔒 app/privacy_filter.py — 隐私过滤器

**为什么需要？** 未来接入云端大模型时，敏感信息（API Key、路径、个人信息）
需要在发送前脱敏，收到回复后还原。

---

### 🌐 app/wechat_bridge.py — 微信桥接

**为什么需要？** 计划让 LocalMindDesk 能通过微信接收指令和回复消息。

---

### 👷 app/worker.py — 并行任务调度

**为什么需要？** 复杂任务需要拆分成多个子任务并行执行。

---

## 🎨 frontend/ — 前端界面

只有 **3 个文件**，但构成了整个用户界面：

### frontend/index.html — 页面结构

**为什么需要？** 定义"页面上有什么元素"。

```
页面结构:
├── 标题栏 (titlebar) — 最小化/最大化/关闭按钮
├── 侧边栏 (sidebar) — 对话列表 + Agent 信息 + 记忆面板
├── 主区域 (mainArea)
│   ├── 顶栏 — Context 进度条 + 模型选择
│   ├── 消息区 — 所有对话消息
│   └── 输入区 — 文本框 + 发送/停止按钮
├── 设置面板 — 模型端点/个性化/技能/参数
└── 右侧工作区 (workspace) — 文件树 + 代码预览 + 操作日志
```

### frontend/style.css — 样式（38KB！）

**为什么这么大？** 因为整个界面的视觉效果全靠它：
- 暗色主题颜色体系（VS Code 风格）
- 所有组件的样式（按钮、消息气泡、侧边栏等）
- 动画效果（脉冲、渐变、悬停效果）
- 响应式布局（手机/电脑适配）

**关键设计变量（CSS 自定义属性）**：
```css
:root {
  --bg-0: #1e1e1e;        /* 最深背景（编辑器主体） */
  --accent: #10b981;      /* 品牌色（翡翠绿） */
  --error: #f14c4c;       /* 错误/停止色（红） */
  --text-1: #e6edf3;      /* 主文字 */
}
```

### frontend/app.js — 交互逻辑（55KB！）

**为什么这么大？** 因为所有前端逻辑都在这一个文件里：

```javascript
// 主要功能模块：
sendMessage()        // 发消息给后端
stopGenerating()     // 中断对话（红色停止键）
setSendButtonState() // 切换发送/停止按钮状态
loadConfig()         // 加载模型配置
checkHealth()        // 检测后端是否在线
loadFileTree()       // 加载文件树
openFile()           // 打开文件预览
appendMsg()          // 在界面上添加消息气泡
renderActivityFeed() // 渲染 Agent 活动流
updateContextBar()   // 更新 Token 使用量
loadSessions()       // 加载历史会话
// ... 还有很多
```

---

## 🖥️ electron/ — 桌面应用壳

**为什么需要？** 把网页变成独立的桌面应用（像 VS Code 那样）。

### electron/main.js — Electron 主进程

```javascript
// 创建一个桌面窗口
const win = new BrowserWindow({
  width: 1400, height: 900,
  frame: false,  // 去掉系统标题栏，用自定义的
});

// 窗口加载前端页面
win.loadFile('frontend/index.html');

// 启动 Python 后端
// → 运行 uvicorn app.main:app
```

### electron/preload.js — 预加载脚本

**为什么需要？** 浏览器页面不能直接操作系统（安全原因）。
preload 提供了一个"安全桥梁"，让前端能调用 Electron 的功能（如打开文件夹对话框）。

### electron/python-bridge.js — Python 后端启动器

**为什么需要？** Electron 需要同时启动 Python 后端进程。
这个文件负责：找到 Python → 启动后端 → 监控健康状态 → 程序关闭时杀掉后端。

---

## 📝 doc/ — 文档目录

**为什么需要？** 记录所有开发进展、设计方案、架构分析。

重要文档：
- `progress_summary.md` — 开发进展总纲（每次改动都更新）
- `evolution_plan_thinking_assistant.md` — 思维引擎进化方案
- `ui_redesign_and_wechat_plan.md` — UI 重设计 + 微信集成方案
- `action_agent_architecture.md` — Action Agent 架构设计

---

## 🤖 .agents/ — Agent Prompt 文件

**为什么需要？** 不同的"子 Agent"需要不同的系统提示词。

```
.agents/
├── action_agent.md  — Action Agent 的系统 prompt
├── meta_agent.md    — Meta Agent（自进化）的系统 prompt
├── intent_router.md — 意图路由器的系统 prompt
└── tool_router.md   — 工具路由器的系统 prompt
```

---

## ⚙️ 配置文件

### config.json — 全局配置
```json
{
  "active_model": "local-lmstudio",    // 当前使用的模型
  "temperature": 0.7,                   // AI 随机性（0=确定 1=创意）
  "max_tokens": 131072,                 // 最大 token 数
  "server_port": 8000,                  // 后端端口
  "system_prompt": "你是 LocalMindDesk...",  // AI 人格提示词
  "models": [...]                       // 可用的模型端点列表
}
```

### requirements.txt — Python 依赖
```
fastapi         # Web 框架
uvicorn         # ASGI 服务器
openai          # 调用 LM Studio 的 API
pydantic        # 数据验证
python-pptx     # 生成 PPT
python-docx     # 生成 Word
pyautogui       # GUI 自动化（截图/点击）
psutil          # 进程管理
```

### package.json — Node/Electron 依赖
```json
{
  "name": "localminddesk",
  "main": "electron/main.js",
  "scripts": {
    "start": "electron ."   // 启动桌面应用
  }
}
```

---

## 🔄 数据流：用户说一句话，发生了什么？

以用户输入 **"帮我在 test.py 里写一个贪吃蛇游戏"** 为例：

```
1. [前端 app.js] 用户按 Enter
   → sendMessage() 被调用
   → fetch("/api/chat", { message: "帮我在 test.py 里写一个贪吃蛇游戏" })

2. [后端 main.py] 收到 POST /api/chat
   → 从数据库加载历史消息
   → 组装三层记忆（热窗口 + 长期 + 向量）
   → 调用 agent_router.route()

3. [agent_router.py] route() 函数
   → thinking_engine.detect_mode() → "execute"（明确的创建指令）
   → build_enhanced_prompt() → 构建增强版 system prompt
   → analyze_intents() → ["action"]（检测到操作意图）
   → 调用 _exec_action()

4. [action_planner.py] plan_actions()
   → 正则匹配到 "在 test.py 里写"
   → 走 _try_code_to_file() 路径

5. [agent_router.py] _try_code_to_file()
   → 调用 LLM 生成贪吃蛇代码
   → 调用 file_tool.execute() 写入 test.py

6. [file_tool.py] execute()
   → 创建文件 test.py，写入生成的代码
   → 返回 {"success": True}

7. [agent_router.py] 组装结果
   → {"reply": "✓ 已生成代码...", "file_changed": True}

8. [main.py] 返回 JSON 给前端

9. [前端 app.js] 收到响应
   → appendMsg() 显示 AI 回复
   → loadFileTree() 刷新文件树（因为 file_changed=True）
   → 用户在右侧看到新创建的 test.py
```

---

## 🎯 核心设计决策总结

| 决策 | 为什么这样做 |
|------|-------------|
| **前后端分离** | 前端可以跑在浏览器或 Electron，后端可以独立部署 |
| **FastAPI** | Python 生态最快的 Web 框架，支持异步 |
| **Electron** | 把网页变成桌面应用，跨平台（Win/Mac/Linux） |
| **正则匹配意图** | 比 LLM 分析快 100 倍，简单指令足够准确 |
| **工具注册制** | 新增工具只需写一个类 + 注册一行，不需要改核心代码 |
| **SQLite** | 轻量级，单文件数据库，不需要安装数据库服务器 |
| **CSS 变量** | 改一个变量就能换整个主题颜色 |
| **System Prompt 分层** | 基础人格 + 模式指令 + 项目上下文，灵活组合 |
