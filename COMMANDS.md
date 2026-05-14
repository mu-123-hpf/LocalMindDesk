# LocalMindDesk — 命令速查

> Clone 项目后进入根目录即可

---

## 🚀 启动方式（三种）

### 方式一：双击 start.bat（最简单）
```
直接双击 start.bat，选择菜单选项即可
```

### 方式二：命令行手动启动

#### ① 仅启动后端（API 服务）
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
- 后端地址: http://localhost:8000
- `--reload`: 代码变更自动重启（开发用）
- 去掉 `--reload` 可用于生产

#### ② 网页版（需后端运行中）
```bash
# 先启动后端（另开一个终端）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 然后浏览器访问
http://localhost:8000
```

#### ③ Electron App
```bash
npm run dev      # 开发模式（有 DevTools）
npm start        # 正式模式
```

#### ④ CLI 终端对话（不需要后端）
```bash
python cli.py                      # 默认聊天
python cli.py -p <角色slug>        # 指定角色
python cli.py --mode plan          # 规划模式
python cli.py --no-color           # 无颜色（适合日志/管道）
```

### 方式三：打包发布版（App 安装包）
```bash
build.bat        # 一键打包 Electron 安装程序
# 产物在 dist\ 目录
```

---

## 💬 CLI 内置命令

进入 CLI 对话后，支持以下命令：

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助 |
| `/persona` | 列出所有角色 |
| `/persona <slug>` | 切换角色 |
| `/mode` | 查看当前对话模式 |
| `/mode chat` | 切换到聊天模式 |
| `/mode plan` | 切换到规划模式 |
| `/mode execute` | 切换到执行模式 |
| `/mode review` | 切换到审查模式 |
| `/clear` | 清空对话历史 |
| `/memory` | 查看长期记忆 |
| `/status` | 查看模型/角色/历史状态 |
| `exit` / `q` | 退出 |

---

## 📦 开发指令

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Node 依赖（Electron）
npm install

# 打包 Python 后端（PyInstaller）
npm run build:python

# 打包完整 Electron 安装包
npm run dist

# 或者直接用 build.bat
build.bat
```

---

## 🗂️ 各模式对比

| 模式 | 命令 | 是否需要后端 | 适合场景 |
|------|------|-------------|---------|
| CLI | `python cli.py` | ❌ 不需要 | 快速对话、脚本集成 |
| 网页版 | 浏览器 `localhost:8000` | ✅ 需要 | 完整功能、多设备 |
| Electron App | `npm run dev` | ✅ 自动启动 | 桌面体验 |
| 微信桥接 | 随后端自动启动 | ✅ 需要 | 微信远程控制 |

---

## ⚙️ 环境要求

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 后端 + CLI |
| Node.js | 18+ | Electron App |
| LM Studio | 最新版 | 本地模型（或配置云端 API） |

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
# 确保后端已在 8000 端口运行
python -m uvicorn app.main:app --port 8000
```

**Q: 模型无响应**
- 检查 LM Studio 是否运行，且 API Server 已开启
- 检查 `config.json` 中 `base_url` 配置是否正确
