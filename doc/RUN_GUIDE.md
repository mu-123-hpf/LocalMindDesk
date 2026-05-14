# LocalMindDesk — 运行指南

> Clone 项目后进入根目录即可

---

## 📋 前置条件

在运行任何模式之前，请确保已安装以下环境：

| 依赖 | 版本要求 | 用途 | 安装检查 |
|------|---------|------|---------|
| **Python** | 3.10+ | 后端 API + CLI | `python --version` |
| **Node.js** | 18+ | Electron App | `node --version` |
| **LM Studio** | 最新版 | 本地模型推理 | 打开 LM Studio 界面 |

### 一键安装依赖

```bash
# 在项目根目录执行
cd "your-project-path"

# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Node.js 依赖（Electron）
npm install
```

### 模型配置

项目默认使用 LM Studio 本地模型。确保：

1. **LM Studio 已打开**，且加载了模型（在 `config.json` 中配置模型名称）
2. **LM Studio API Server 已开启**（默认 `http://127.0.0.1:1234/v1`）
3. 可在 `config.json` 中修改模型配置（也支持云端 API）

---

## 🚀 三种运行方式

### ⓪ 最简单：双击 start.bat

```
直接双击项目根目录的 start.bat
会出现菜单让你选择启动模式（1~6）
```

---

### ① CLI 终端对话模式（最轻量）

> **提示**: CLI 模式**不需要**启动后端服务，直接连接 LM Studio 本地模型对话。最适合快速聊天和脚本集成。

```bash
cd "your-project-path"

# 基本用法 — 直接开始聊天
python cli.py

# 指定角色
python cli.py --persona my-girl

# 指定对话模式（chat/plan/execute/review）
python cli.py --mode plan

# 禁用颜色输出（适合日志/管道）
python cli.py --no-color
```

**入口文件**: `cli.py`

**CLI 内置命令**（对话过程中输入）：

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助 |
| `/persona` | 列出所有角色 |
| `/persona <slug>` | 切换角色 |
| `/mode <模式>` | 切换模式: chat / plan / execute / review |
| `/clear` | 清空对话历史 |
| `/memory` | 查看长期记忆 |
| `/status` | 查看模型/角色状态 |
| `exit` / `quit` / `q` | 退出 |

---

### ② 网页版（完整功能）

> **重要**: 网页版需要**先启动 Python 后端**，后端会同时托管前端静态页面。

#### 方法 A：一条命令启动（开发模式，热重载）

```bash
cd "your-project-path"
npm run backend
```

或者直接用 Python：

```bash
cd "your-project-path"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

然后浏览器打开 👉 **http://localhost:8000**

#### 方法 B：生产模式（无热重载）

```bash
cd "your-project-path"
npm run backend:prod
```

#### 方法 C：通过 start.bat 菜单

```
双击 start.bat → 选择 [2] 启动网页版
```

> 会自动在后台启动后端并打开浏览器。

**入口文件**:

- 后端: `app/main.py` (FastAPI, 端口 8000)
- 前端: `frontend/index.html` (由后端托管)

---

### ③ Electron 桌面 App

> **重要**: Electron 会**自动启动 Python 后端**（通过 `python-bridge.js`），无需手动启动。

#### 开发模式（带 DevTools）

```bash
cd "your-project-path"
npm run dev
```

#### 正式模式

```bash
cd "your-project-path"
npm start
```

#### 通过 start.bat 菜单

```
双击 start.bat → 选择 [3] 启动 Electron App
```

**入口文件**:

- Electron 主进程: `electron/main.js`
- Python 桥接: `electron/python-bridge.js`
- 预加载脚本: `electron/preload.js`

---

## 📂 npm scripts 速查

| 命令 | 说明 |
|------|------|
| `npm run backend` | 启动后端（开发模式，热重载） |
| `npm run backend:prod` | 启动后端（生产模式） |
| `npm run cli` | 启动 CLI 对话 |
| `npm run dev` | Electron 开发模式 |
| `npm start` | Electron 正式模式 |
| `npm run build:python` | PyInstaller 打包 Python 后端 |
| `npm run build` | electron-builder 打包 |
| `npm run dist` | 一步完成 Python + Electron 打包 |

---

## 📦 打包发布

将项目打包成可分发的 Windows 安装程序：

```bash
cd "your-project-path"

# 方法 1：一键打包（推荐）
.\build.bat

# 方法 2：分步打包
npm run build:python    # 先用 PyInstaller 打包 Python 后端
npm run build           # 再用 electron-builder 打包 Electron

# 方法 3：一步到位
npm run dist            # 等于 build:python + build
```

打包产物在 `dist\` 目录。

打包配置文件: `electron-builder.yml`

---

## 🗂️ 模式对比总览

| 模式 | 启动命令 | 需要后端？ | 需要 Node？ | 适合场景 |
|------|---------|-----------|------------|---------|
| **CLI** | `python cli.py` | ❌ 不需要 | ❌ 不需要 | 快速对话、脚本集成、服务器环境 |
| **网页版** | `npm run backend` → 浏览器 `localhost:8000` | ✅ 需要 | ❌ 不需要 | 完整功能、多设备访问、开发调试 |
| **Electron App** | `npm run dev` 或 `npm start` | ✅ 自动启动 | ✅ 需要 | 桌面体验、桌宠、无边框窗口 |
| **微信桥接** | 随后端自动启动 | ✅ 需要 | ❌ 不需要 | 微信远程控制 |

---

## 🔧 常见问题

**Q: 后端启动报错 `uvicorn not found`**

```bash
pip install uvicorn fastapi
```

**Q: CLI 启动报错 `No module named 'app'`**

```bash
# 确保在项目根目录运行
cd "your-project-path"
python cli.py
```

**Q: Electron 启动白屏**

```bash
# 检查后端是否在 8000 端口运行
python -m uvicorn app.main:app --port 8000
```

**Q: 模型无响应**

- 检查 LM Studio 是否运行，且 **API Server 已开启**
- 检查 `config.json` 中 `base_url` 是否为 `http://127.0.0.1:1234/v1`

**Q: npm install 失败**

```bash
# 清除缓存重试
npm cache clean --force
npm install
```

---

## 📁 关键文件索引

```
localminddesk lm/
├── start.bat              ← 启动菜单（双击即用）
├── build.bat              ← 一键打包
├── cli.py                 ← CLI 对话入口
├── config.json            ← 模型/系统配置
├── requirements.txt       ← Python 依赖
├── package.json           ← Node 依赖 + npm scripts
├── electron-builder.yml   ← Electron 打包配置
│
├── app/                   ← Python 后端（FastAPI）
│   ├── main.py            ← 后端主入口 + 所有 API
│   ├── agent_router.py    ← AI 路由/对话核心
│   ├── config.py          ← 配置管理
│   ├── memory.py          ← 会话/记忆管理
│   ├── soul_manager.py    ← 角色系统
│   └── ...
│
├── electron/              ← Electron 桌面壳
│   ├── main.js            ← 主进程（窗口 + IPC）
│   ├── python-bridge.js   ← 自动启/停 Python 后端
│   └── preload.js         ← 渲染进程预加载
│
├── frontend/              ← 前端 UI
│   ├── index.html         ← 主页面
│   ├── app.js             ← 前端逻辑
│   ├── style.css          ← 样式
│   ├── pet-desktop.html   ← 桌宠独立窗口
│   └── assets/            ← 静态资源
│
└── data/                  ← 运行时数据
```

---

*LocalMindDesk v2.0 — MIT License*
