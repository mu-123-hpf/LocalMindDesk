"""
LocalMindDesk — 微信远程操作模块 (Phase 5.2 + 5.4)

支持通过微信远程控制电脑：
1. 截屏 → 发回微信
2. 系统状态查询（CPU/内存/磁盘）
3. 文件搜索/读取
4. 执行终端命令（受限）
5. 打开文件/URL
"""
import os
import re
import time
import platform
import subprocess
from typing import Optional


# ============================================================
#  远程操作命令检测
# ============================================================

# 命令模式 → (操作类型, 参数提取)
REMOTE_PATTERNS = [
    # 截屏
    (re.compile(r'(?:截[个张]?屏|screenshot|截图|屏幕截图)', re.I), 'screenshot', None),
    # 系统状态
    (re.compile(r'(?:电脑状态|系统状态|系统信息|查.*(?:CPU|内存|磁盘|硬盘)|system\s*status)', re.I), 'sysinfo', None),
    # 打开文件
    (re.compile(r'(?:打开文件|open\s+file)\s*[：:]*\s*(.+)', re.I), 'open_file', 1),
    # 搜索文件
    (re.compile(r'(?:搜索文件|查找文件|找.*文件|search\s+file)\s*[：:]*\s*(.+)', re.I), 'search_file', 1),
    # 读取文件
    (re.compile(r'(?:读取文件|查看文件|看.*文件|read\s+file|cat)\s*[：:]*\s*(.+)', re.I), 'read_file', 1),
    # 执行命令
    (re.compile(r'(?:执行命令|运行命令|终端|terminal|cmd|run)\s*[：:]*\s*(.+)', re.I), 'run_cmd', 1),
    # 打开URL
    (re.compile(r'(?:打开网页|打开链接|open\s+url)\s*[：:]*\s*(.+)', re.I), 'open_url', 1),
    # 关机/重启（需二次确认）
    (re.compile(r'(?:关机|shutdown|重启|restart|reboot)', re.I), 'power', None),
]

# 危险命令黑名单
DANGEROUS_COMMANDS = [
    r'\brm\s+-rf\b', r'\bdel\s+/[sfq]\b', r'\bformat\b',
    r'\bdd\s+if=\b', r'\bmkfs\b', r'\bfdisk\b',
    r'\breg\s+delete\b', r'\bnet\s+user\b',
]
_DANGEROUS_RE = [re.compile(p, re.I) for p in DANGEROUS_COMMANDS]


def detect_remote_command(text: str) -> Optional[dict]:
    """
    检测微信消息是否为远程操作命令

    Returns:
        None — 不是远程命令
        {"op": str, "param": str, "needs_confirm": bool} — 是远程命令
    """
    text = text.strip()
    for pattern, op, group_idx in REMOTE_PATTERNS:
        match = pattern.search(text)
        if match:
            param = match.group(group_idx).strip() if group_idx else ""
            needs_confirm = op in ('run_cmd', 'power', 'open_file')
            return {"op": op, "param": param, "needs_confirm": needs_confirm}
    return None


# ============================================================
#  操作执行器
# ============================================================

def execute_remote_op(op: str, param: str = "") -> dict:
    """
    执行远程操作

    Returns:
        {
            "success": bool,
            "message": str,         # 文本结果
            "file_path": str|None,  # 生成的文件路径（截图等）
        }
    """
    try:
        if op == "screenshot":
            return _do_screenshot()
        elif op == "sysinfo":
            return _do_sysinfo()
        elif op == "open_file":
            return _do_open_file(param)
        elif op == "search_file":
            return _do_search_file(param)
        elif op == "read_file":
            return _do_read_file(param)
        elif op == "run_cmd":
            return _do_run_cmd(param)
        elif op == "open_url":
            return _do_open_url(param)
        elif op == "power":
            return {"success": False, "message": "⚠️ 关机/重启功能已禁用，请手动操作"}
        else:
            return {"success": False, "message": f"未知操作: {op}"}
    except Exception as e:
        return {"success": False, "message": f"执行失败: {str(e)[:200]}"}


def _do_screenshot() -> dict:
    """截屏并保存到临时文件"""
    try:
        from PIL import ImageGrab
    except ImportError:
        return {"success": False, "message": "截屏需要 Pillow 库，请安装: pip install Pillow"}

    os.makedirs("data/temp", exist_ok=True)
    ts = int(time.time())
    path = f"data/temp/screenshot_{ts}.png"

    try:
        img = ImageGrab.grab()
        img.save(path, "PNG")
        return {
            "success": True,
            "message": f"📸 屏幕截图已完成 ({img.size[0]}x{img.size[1]})",
            "file_path": os.path.abspath(path),
        }
    except Exception as e:
        return {"success": False, "message": f"截屏失败: {e}"}


def _do_sysinfo() -> dict:
    """获取系统状态"""
    info_parts = []

    # 基本信息
    info_parts.append(f"💻 {platform.node()}")
    info_parts.append(f"🖥 {platform.system()} {platform.release()}")

    try:
        import psutil
        # CPU
        cpu_pct = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        info_parts.append(f"⚡ CPU: {cpu_pct}% ({cpu_count}核)")

        # 内存
        mem = psutil.virtual_memory()
        mem_used = mem.used / (1024**3)
        mem_total = mem.total / (1024**3)
        info_parts.append(f"🧠 内存: {mem_used:.1f}GB / {mem_total:.1f}GB ({mem.percent}%)")

        # 磁盘
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                used_gb = usage.used / (1024**3)
                total_gb = usage.total / (1024**3)
                info_parts.append(f"💾 {part.device}: {used_gb:.0f}GB / {total_gb:.0f}GB ({usage.percent}%)")
            except Exception:
                pass

        # 网络
        net = psutil.net_io_counters()
        sent_mb = net.bytes_sent / (1024**2)
        recv_mb = net.bytes_recv / (1024**2)
        info_parts.append(f"🌐 网络: ↑{sent_mb:.0f}MB ↓{recv_mb:.0f}MB")

        # 开机时间
        import datetime
        boot = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.datetime.now() - boot
        hours = int(uptime.total_seconds() // 3600)
        info_parts.append(f"⏱ 已开机: {hours}小时")

    except ImportError:
        # psutil 不可用，用基础方式
        if platform.system() == "Windows":
            try:
                result = subprocess.run(
                    ["wmic", "OS", "get", "FreePhysicalMemory,TotalVisibleMemorySize", "/value"],
                    capture_output=True, text=True, timeout=10,
                )
                info_parts.append(result.stdout.strip()[:200])
            except Exception:
                info_parts.append("(安装 psutil 可获取详细信息)")

    return {"success": True, "message": "\n".join(info_parts)}


def _do_open_file(path: str) -> dict:
    """打开文件（用系统默认程序）"""
    path = path.strip().strip('"').strip("'")
    if not os.path.exists(path):
        return {"success": False, "message": f"文件不存在: {path}"}

    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return {"success": True, "message": f"✅ 已打开: {os.path.basename(path)}"}
    except Exception as e:
        return {"success": False, "message": f"打开失败: {e}"}


def _do_search_file(query: str) -> dict:
    """搜索文件"""
    query = query.strip()
    if not query:
        return {"success": False, "message": "请指定搜索关键词"}

    results = []

    # 在常见位置搜索
    search_dirs = [
        os.path.expanduser("~\\Desktop"),
        os.path.expanduser("~\\Documents"),
        os.path.expanduser("~\\Downloads"),
        "D:\\",
    ]

    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        try:
            for root, dirs, files in os.walk(search_dir):
                # 限制搜索深度
                depth = root.replace(search_dir, "").count(os.sep)
                if depth > 3:
                    dirs.clear()
                    continue
                # 跳过隐藏和系统目录
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in
                           ('node_modules', '__pycache__', '.git', 'AppData')]
                for f in files:
                    if query.lower() in f.lower():
                        full = os.path.join(root, f)
                        size_kb = os.path.getsize(full) / 1024
                        results.append(f"📄 {full} ({size_kb:.0f}KB)")
                        if len(results) >= 15:
                            break
                if len(results) >= 15:
                    break
        except Exception:
            continue

    if not results:
        return {"success": True, "message": f"🔍 未找到匹配 \"{query}\" 的文件"}

    msg = f"🔍 找到 {len(results)} 个文件:\n" + "\n".join(results)
    return {"success": True, "message": msg}


def _do_read_file(path: str) -> dict:
    """读取文件内容"""
    path = path.strip().strip('"').strip("'")
    if not os.path.isfile(path):
        return {"success": False, "message": f"文件不存在: {path}"}

    size = os.path.getsize(path)
    if size > 100 * 1024:
        return {"success": False, "message": f"文件太大 ({size/1024:.0f}KB)，最大支持 100KB"}

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        return {"success": False, "message": f"读取失败: {e}"}

    # 截断显示
    if len(content) > 2000:
        content = content[:1800] + f"\n\n... (共 {len(content)} 字，已截断)"

    fname = os.path.basename(path)
    return {"success": True, "message": f"📄 {fname}:\n\n{content}"}


def _do_run_cmd(cmd: str) -> dict:
    """执行终端命令（安全限制）"""
    cmd = cmd.strip()
    if not cmd:
        return {"success": False, "message": "请指定要执行的命令"}

    # 安全检查：危险命令拦截
    for pattern in _DANGEROUS_RE:
        if pattern.search(cmd):
            return {"success": False, "message": f"⛔ 危险命令已拦截: {cmd[:50]}"}

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=30, cwd=os.path.expanduser("~"),
        )
        output = result.stdout or ""
        error = result.stderr or ""

        # 截断输出
        if len(output) > 2000:
            output = output[:1800] + "\n... (已截断)"
        if len(error) > 500:
            error = error[:400] + "\n... (已截断)"

        msg = f"🖥 执行: {cmd}\n"
        if result.returncode == 0:
            msg += f"✅ 退出码: 0\n"
        else:
            msg += f"⚠️ 退出码: {result.returncode}\n"
        if output:
            msg += f"\n{output}"
        if error:
            msg += f"\n⚠️ 错误:\n{error}"

        return {"success": result.returncode == 0, "message": msg}

    except subprocess.TimeoutExpired:
        return {"success": False, "message": f"⏰ 命令超时 (30秒): {cmd[:50]}"}
    except Exception as e:
        return {"success": False, "message": f"执行失败: {e}"}


def _do_open_url(url: str) -> dict:
    """打开 URL"""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        import webbrowser
        webbrowser.open(url)
        return {"success": True, "message": f"🌐 已打开: {url}"}
    except Exception as e:
        return {"success": False, "message": f"打开失败: {e}"}
