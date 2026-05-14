#!/usr/bin/env python3
"""
LocalMindDesk — 终端 CLI 对话模式
======================================
用法:
    python cli.py                  # 默认聊天
    python cli.py --persona slug   # 指定角色
    python cli.py --mode plan      # 指定对话模式
    python cli.py --no-color       # 禁用颜色输出

内置命令（对话中输入）:
    /help              查看帮助
    /persona [slug]    列出或切换角色
    /mode [模式]       切换对话模式 (chat/plan/execute/review)
    /clear             清空对话历史
    /memory            查看长期记忆
    /status            查看当前状态
    exit / quit / q    退出
"""
import os
import sys

# Windows 终端 UTF-8 兼容
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import argparse
import textwrap
import time
import threading

# ── 项目根目录加入 PATH ────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── ANSI 颜色 ──────────────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    GREEN   = "\033[32m"
    CYAN    = "\033[36m"
    YELLOW  = "\033[33m"
    MAGENTA = "\033[35m"
    RED     = "\033[31m"
    WHITE   = "\033[37m"
    GRAY    = "\033[90m"
    BG_DARK = "\033[40m"

_use_color = True

def c(text, *codes):
    if not _use_color:
        return text
    return "".join(codes) + str(text) + C.RESET


# ── Banner ─────────────────────────────────────────
BANNER = """
╔══════════════════════════════════════════════════╗
║   LocalMindDesk  —  CLI 对话模式            ║
║   输入 /help 查看命令  |  Ctrl+C 或 exit 退出     ║
╚══════════════════════════════════════════════════╝"""

HELP_TEXT = """
{bold}可用命令:{reset}
  /help              显示此帮助
  /persona           列出所有可用角色
  /persona <slug>    切换到指定角色（slug 是角色标识）
  /mode              查看当前对话模式
  /mode <模式>       切换模式: chat / plan / execute / review
  /clear             清空当前对话历史
  /memory            查看已提取的长期记忆
  /status            查看模型和角色状态
  exit / quit / q    退出

{bold}对话模式说明:{reset}
  chat     —  日常聊天，简洁回答
  plan     —  深度规划，分步分析
  execute  —  执行模式，直接操作
  review   —  审查模式，批判性评估
"""


# ── 加载动画 ────────────────────────────────────────
class Spinner:
    FRAMES = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

    def __init__(self, label="思考中"):
        self.label = label
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        # 清除 spinner 行
        sys.stdout.write("\r" + " " * (len(self.label) + 5) + "\r")
        sys.stdout.flush()

    def _run(self):
        i = 0
        while not self._stop.is_set():
            frame = self.FRAMES[i % len(self.FRAMES)]
            if _use_color:
                sys.stdout.write(f"\r{C.CYAN}{frame}{C.RESET} {C.DIM}{self.label}...{C.RESET}")
            else:
                sys.stdout.write(f"\r{frame} {self.label}...")
            sys.stdout.flush()
            i += 1
            time.sleep(0.08)


# ── 输出工具 ────────────────────────────────────────
def print_banner():
    print(c(BANNER, C.CYAN, C.BOLD))

def print_help():
    print(HELP_TEXT.format(bold=C.BOLD if _use_color else "",
                           reset=C.RESET if _use_color else ""))

def print_ai(text: str, persona_name: str = "AI"):
    """打印 AI 回复，带折行"""
    prefix = c(f"\n✨ {persona_name}:", C.GREEN, C.BOLD)
    print(prefix)
    # 按段落折行输出（每行最大 80 字符，对中文友好）
    for para in text.split("\n"):
        if para.strip():
            print(textwrap.fill(para, width=80, subsequent_indent="   ") if len(para) > 80 else para)
        else:
            print()
    print()

def print_info(msg: str):
    print(c(f"  ℹ  {msg}", C.CYAN))

def print_warn(msg: str):
    print(c(f"  ⚠  {msg}", C.YELLOW))

def print_error(msg: str):
    print(c(f"  ✗  {msg}", C.RED))

def print_success(msg: str):
    print(c(f"  ✓  {msg}", C.GREEN))

def print_sep():
    print(c("─" * 50, C.GRAY))


# ── CLI 核心 ────────────────────────────────────────
class LocalMindDeskCLI:
    def __init__(self, persona_slug: str = None, mode: str = "chat"):
        self.history = []
        self.mode = mode
        self.persona_name = "LocalMindDesk"
        self.persona_slug = persona_slug
        self._init_modules()
        self._load_persona(persona_slug)

    def _init_modules(self):
        """懒加载所有后端模块（避免循环依赖和冷启动慢）"""
        print_info("正在初始化...")
        try:
            from app.config import get_config, load_config
            load_config()
            cfg = get_config()
            ep = None
            for m in cfg.models:
                if m.name == cfg.active_model and m.is_active:
                    ep = m
                    break
            if ep:
                print_success(f"模型: {ep.name} ({ep.provider})")
            else:
                print_warn("未找到激活的模型配置，请检查 config.json")
        except Exception as e:
            print_warn(f"配置加载失败: {e}")

        try:
            from app import agent_router  # noqa — 触发模块初始化
            self._router = agent_router
        except Exception as e:
            print_error(f"路由模块加载失败: {e}")
            sys.exit(1)

        try:
            from app.memory import create_session
            self._session_id = create_session()
        except Exception:
            self._session_id = None

    def _load_persona(self, slug: str = None):
        """加载角色"""
        try:
            from app.soul_manager import get_soul_manager
            sm = get_soul_manager()
            if slug:
                result = sm.switch_persona(slug)
                if result.get("success"):
                    self.persona_name = result.get("name", slug)
                    self.persona_slug = slug
                    print_success(f"已切换角色: {self.persona_name}")
                else:
                    print_warn(f"角色切换失败: {result.get('error', '未知错误')}")
            elif sm.has_soul:
                # 使用当前激活的角色
                identity = sm.get_identity("pc")
                if identity:
                    self.persona_name = sm._active_slug or "LocalMindDesk"
                    print_success(f"当前角色: {self.persona_name}")
        except Exception:
            pass  # 无角色时使用默认 prompt

    def _build_prompt(self) -> str:
        """构建系统 prompt"""
        from app.config import get_config
        cfg = get_config()
        prompt = cfg.system_prompt

        try:
            from app.soul_manager import get_soul_manager
            sm = get_soul_manager()
            if sm.has_soul:
                ctx = sm.get_identity("pc")
                if ctx:
                    prompt = ctx
        except Exception:
            pass

        try:
            from app.memory import get_memory_text
            mem = get_memory_text()
            if mem:
                prompt += f"\n\n[长期记忆]:\n{mem}"
        except Exception:
            pass

        return prompt

    def _cmd_list_personas(self):
        """列出所有角色"""
        try:
            from app.soul_manager import get_soul_manager
            sm = get_soul_manager()
            personas = sm.list_personas()
            if not personas:
                print_info("暂无角色。使用网页版或 App 创建角色后即可在 CLI 使用。")
                return
            print(c("\n可用角色:", C.BOLD))
            for p in personas:
                active_mark = c(" ← 当前", C.GREEN) if p.get("slug") == self.persona_slug else ""
                print(f"  • {c(p.get('slug',''), C.CYAN)}  —  {p.get('name','')}{active_mark}")
            print()
        except Exception as e:
            print_warn(f"无法获取角色列表: {e}")

    def _cmd_memory(self):
        """查看长期记忆"""
        try:
            from app.memory import get_memory_text
            mem = get_memory_text()
            if not mem:
                print_info("暂无长期记忆")
                return
            print(c("\n📚 长期记忆:", C.BOLD))
            for line in mem.split("\n")[:20]:
                if line.strip():
                    print(f"  {line}")
            print()
        except Exception as e:
            print_warn(f"无法获取记忆: {e}")

    def _cmd_status(self):
        """查看状态"""
        try:
            from app.config import get_config
            cfg = get_config()
            ep = None
            for m in cfg.models:
                if m.name == cfg.active_model and m.is_active:
                    ep = m
                    break
            print(c("\n📊 当前状态:", C.BOLD))
            print(f"  模型  : {c(cfg.active_model, C.CYAN)}")
            if ep:
                print(f"  端点  : {ep.base_url}")
            print(f"  角色  : {c(self.persona_name, C.GREEN)}")
            print(f"  模式  : {c(self.mode, C.YELLOW)}")
            print(f"  历史  : {len(self.history)} 条消息")
            print()
        except Exception as e:
            print_warn(f"状态获取失败: {e}")

    def handle_command(self, cmd: str) -> bool:
        """
        处理 /xxx 命令。
        返回 True 表示继续对话，False 表示退出。
        """
        parts = cmd.strip().split(maxsplit=1)
        verb = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if verb == "/help":
            print_help()

        elif verb == "/persona":
            if not arg:
                self._cmd_list_personas()
            else:
                self._load_persona(arg)

        elif verb == "/mode":
            VALID = {"chat", "plan", "execute", "review"}
            if not arg:
                print_info(f"当前模式: {self.mode}  (可选: {', '.join(VALID)})")
            elif arg in VALID:
                self.mode = arg
                print_success(f"已切换到 {arg} 模式")
            else:
                print_warn(f"无效模式: {arg}，可选: {', '.join(VALID)}")

        elif verb == "/clear":
            self.history.clear()
            if self._session_id:
                try:
                    from app.memory import create_session
                    self._session_id = create_session()
                except Exception:
                    pass
            print_success("对话历史已清空")

        elif verb == "/memory":
            self._cmd_memory()

        elif verb == "/status":
            self._cmd_status()

        else:
            print_warn(f"未知命令: {verb}，输入 /help 查看可用命令")

        return True

    def chat(self, user_input: str) -> str:
        """发送消息，返回 AI 回复"""
        prompt = self._build_prompt()

        spinner = Spinner("思考中")
        spinner.start()
        try:
            result = self._router.route(
                user_message=user_input,
                history=self.history[-20:],
                system_prompt=prompt,
                mode=self.mode,
            )
        except Exception as e:
            spinner.stop()
            raise e
        spinner.stop()

        reply = result.get("reply", "（无回复）")

        # 更新历史
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": reply})

        # 保存到数据库
        if self._session_id:
            try:
                from app.memory import add_message
                add_message(self._session_id, "user", user_input)
                add_message(self._session_id, "assistant", reply)
            except Exception:
                pass

        return reply

    def run(self):
        """主循环"""
        print_banner()
        self._cmd_status()

        try:
            while True:
                # 输入提示
                try:
                    prompt_str = c(f"\n>>> ", C.CYAN, C.BOLD)
                    user_input = input(prompt_str).strip()
                except (EOFError, KeyboardInterrupt):
                    print(c("\n\n再见！👋", C.GREEN))
                    break

                if not user_input:
                    continue

                # 退出指令
                if user_input.lower() in {"exit", "quit", "q", "bye", "再见"}:
                    print(c("\n再见！👋", C.GREEN))
                    break

                # 内置命令
                if user_input.startswith("/"):
                    self.handle_command(user_input)
                    continue

                # 正常对话
                try:
                    reply = self.chat(user_input)
                    print_ai(reply, self.persona_name)
                except KeyboardInterrupt:
                    print(c("\n已中断", C.YELLOW))
                    continue
                except Exception as e:
                    print_error(f"对话失败: {e}")
                    continue

        except KeyboardInterrupt:
            print(c("\n\n再见！👋", C.GREEN))


# ── 入口 ────────────────────────────────────────────
def main():
    global _use_color

    parser = argparse.ArgumentParser(
        description="LocalMindDesk — 终端 CLI 对话",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        示例:
          python cli.py                     # 直接开始聊天
          python cli.py --persona my-girl   # 使用指定角色
          python cli.py --mode plan         # 规划模式
          python cli.py --no-color          # 禁用颜色（适合日志）
        """)
    )
    parser.add_argument("--persona", "-p", default=None,
                        help="启动时加载的角色 slug")
    parser.add_argument("--mode", "-m", default="chat",
                        choices=["chat", "plan", "execute", "review"],
                        help="对话模式 (默认: chat)")
    parser.add_argument("--no-color", action="store_true",
                        help="禁用 ANSI 颜色输出")
    args = parser.parse_args()

    if args.no_color or not sys.stdout.isatty():
        _use_color = False

    cli = LocalMindDeskCLI(persona_slug=args.persona, mode=args.mode)
    cli.run()


if __name__ == "__main__":
    main()
