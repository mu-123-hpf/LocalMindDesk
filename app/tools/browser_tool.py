"""
LocalMindDesk — BrowserTool (Playwright)
AI 专属浏览器自动化工具

特性:
- AI 专属 Chromium 实例（干净 profile，不含用户数据）
- 可接管之前未关闭的 AI 浏览器
- 支持导航、点击、输入、截屏、读取页面等操作
- 每次操作后自动截图反馈
"""
import os
import json
import time
import base64
from datetime import datetime
from app.tools.base import BaseTool, ToolContext

# AI 浏览器专属数据目录
_AI_BROWSER_DATA = os.path.abspath("data/ai_browser_profile")

# 全局浏览器实例（单例，跨请求共享）
_pw_instance = None
_browser = None
_context = None
_page = None
_CDP_PORT = 9333  # AI 专属端口，不与用户浏览器冲突


def _ensure_browser():
    """确保 AI 专属浏览器已启动，支持接管之前未关闭的实例"""
    global _pw_instance, _browser, _context, _page

    # 已有可用页面 → 直接复用
    if _page and not _page.is_closed():
        try:
            _page.title()  # 验证页面还活着
            return _page
        except Exception:
            pass  # 页面失效，重新连接

    from playwright.sync_api import sync_playwright

    if _pw_instance is None:
        _pw_instance = sync_playwright().start()

    # ★ 尝试接管之前的 AI 浏览器（通过 CDP 端口）
    try:
        _browser = _pw_instance.chromium.connect_over_cdp(f"http://127.0.0.1:{_CDP_PORT}")
        contexts = _browser.contexts
        if contexts and contexts[0].pages:
            _page = contexts[0].pages[-1]  # 取最后一个页面
            print(f"[BrowserTool] 接管已有 AI 浏览器 (页面: {_page.title()[:30]})")
            return _page
    except Exception:
        pass  # 没有正在运行的 AI 浏览器

    # ★ 启动全新的 AI 专属浏览器
    os.makedirs(_AI_BROWSER_DATA, exist_ok=True)

    _browser = _pw_instance.chromium.launch_persistent_context(
        user_data_dir=_AI_BROWSER_DATA,
        headless=False,
        args=[
            f"--remote-debugging-port={_CDP_PORT}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            "--window-size=1280,900",
        ],
        viewport={"width": 1280, "height": 900},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
    )
    _context = _browser
    _page = _browser.pages[0] if _browser.pages else _browser.new_page()

    print(f"[BrowserTool] 已启动 AI 专属浏览器 (CDP:{_CDP_PORT})")
    return _page


def _take_screenshot(page, label: str = "") -> dict:
    """截取当前页面并保存"""
    os.makedirs("data/screenshots", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"browser_{label}_{ts}" if label else f"browser_{ts}"
    path = os.path.abspath(f"data/screenshots/{name}.png")
    page.screenshot(path=path, full_page=False)
    return {"path": path}


def close_browser():
    """关闭 AI 浏览器（供外部调用）"""
    global _pw_instance, _browser, _context, _page
    try:
        if _browser:
            _browser.close()
        if _pw_instance:
            _pw_instance.stop()
    except Exception:
        pass
    _pw_instance = _browser = _context = _page = None


class BrowserTool(BaseTool):
    """Playwright 浏览器自动化工具"""

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return "AI 专属浏览器：导航、点击、输入、截屏、读取网页"

    @property
    def danger_level(self) -> str:
        return "moderate"

    def get_danger_level(self, params: dict) -> str:
        action = params.get("action", "")
        if action in ("screenshot", "read", "get_url"):
            return "safe"
        return "moderate"

    def is_read_only(self, params: dict) -> bool:
        return params.get("action") in ("screenshot", "read", "get_url", "get_title")

    def get_paths(self, params: dict) -> list[str]:
        """浏览器操作不涉及文件系统路径，跳过沙盒检查"""
        return []

    def describe_action(self, params: dict) -> str:
        action = params.get("action", "")
        if action == "open":
            return f"🌐 浏览器打开: {params.get('url', '')[:50]}"
        elif action == "click":
            return f"🖱️ 浏览器点击: {params.get('selector', '')[:40]}"
        elif action == "type":
            return f"⌨️ 浏览器输入: {params.get('text', '')[:30]}"
        elif action == "screenshot":
            return "📸 浏览器截屏"
        elif action == "read":
            return f"📖 读取页面: {params.get('selector', 'body')[:30]}"
        elif action == "search":
            return f"🔍 浏览器搜索: {params.get('query', '')[:30]}"
        elif action == "close":
            return "❌ 关闭浏览器"
        return f"🌐 浏览器: {action}"

    def execute(self, params: dict, ctx: ToolContext = None) -> dict:
        action = params.get("action", "")

        try:
            if action == "close":
                close_browser()
                return {"success": True, "message": "AI 浏览器已关闭"}

            page = _ensure_browser()

            if action == "open":
                return self._open(page, params)
            elif action == "click":
                return self._click(page, params)
            elif action == "type":
                return self._type(page, params)
            elif action == "screenshot":
                return self._screenshot(page)
            elif action == "read":
                return self._read(page, params)
            elif action == "scroll":
                return self._scroll(page, params)
            elif action == "search":
                return self._search(page, params)
            elif action == "back":
                page.go_back()
                page.wait_for_load_state("domcontentloaded", timeout=10000)
                shot = _take_screenshot(page, "back")
                return {"success": True, "message": "已后退", "screenshot": shot["path"]}
            elif action == "forward":
                page.go_forward()
                page.wait_for_load_state("domcontentloaded", timeout=10000)
                shot = _take_screenshot(page, "forward")
                return {"success": True, "message": "已前进", "screenshot": shot["path"]}
            elif action == "refresh":
                page.reload()
                page.wait_for_load_state("domcontentloaded", timeout=10000)
                shot = _take_screenshot(page, "refresh")
                return {"success": True, "message": "已刷新", "screenshot": shot["path"]}
            elif action == "get_url":
                return {"success": True, "url": page.url}
            elif action == "get_title":
                return {"success": True, "title": page.title()}
            elif action == "new_tab":
                global _page
                _page = _context.new_page() if _context else page.context.new_page()
                url = params.get("url", "about:blank")
                if url != "about:blank":
                    _page.goto(url, wait_until="domcontentloaded", timeout=30000)
                return {"success": True, "message": f"已打开新标签页: {url[:50]}"}
            elif action == "execute_js":
                script = params.get("script", "")
                if not script:
                    return {"success": False, "error": "缺少 script 参数"}
                result = page.evaluate(script)
                return {"success": True, "result": str(result)[:2000]}
            elif action == "wait":
                selector = params.get("selector", "")
                timeout = params.get("timeout", 10000)
                page.wait_for_selector(selector, timeout=timeout)
                return {"success": True, "message": f"元素已出现: {selector}"}
            else:
                return {"success": False, "error": f"未知浏览器操作: {action}"}

        except ImportError:
            return {"success": False, "error": "playwright 未安装。运行: pip install playwright && playwright install chromium"}
        except Exception as e:
            return {"success": False, "error": f"浏览器操作失败: {str(e)[:300]}"}

    def _open(self, page, params: dict) -> dict:
        url = params.get("url", "")
        if not url:
            return {"success": False, "error": "缺少 url 参数"}
        # 自动补全 http
        if not url.startswith(("http://", "https://", "file://")):
            url = "https://" + url
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1)  # 等待渲染
        shot = _take_screenshot(page, "open")
        title = page.title()
        return {
            "success": True,
            "message": f"已打开: {title[:50]}",
            "url": page.url,
            "title": title,
            "screenshot": shot["path"],
        }

    def _click(self, page, params: dict) -> dict:
        selector = params.get("selector", "")
        text = params.get("text", "")  # 按文本查找
        if text:
            # 优先按文本查找可点击元素
            loc = page.get_by_text(text, exact=False).first
            loc.click(timeout=10000)
        elif selector:
            page.click(selector, timeout=10000)
        else:
            return {"success": False, "error": "需要 selector 或 text 参数"}
        time.sleep(0.5)
        shot = _take_screenshot(page, "click")
        return {"success": True, "message": f"已点击: {text or selector}", "screenshot": shot["path"]}

    def _type(self, page, params: dict) -> dict:
        selector = params.get("selector", "")
        text = params.get("text", "")
        clear = params.get("clear", True)
        submit = params.get("submit", False)

        if not text:
            return {"success": False, "error": "缺少 text 参数"}

        if selector:
            if clear:
                page.fill(selector, text, timeout=10000)
            else:
                page.type(selector, text, timeout=10000)
        else:
            # 在当前聚焦的元素中输入
            page.keyboard.type(text)

        if submit:
            page.keyboard.press("Enter")
            time.sleep(1)

        shot = _take_screenshot(page, "type")
        return {"success": True, "message": f"已输入: {text[:30]}", "screenshot": shot["path"]}

    def _screenshot(self, page) -> dict:
        shot = _take_screenshot(page, "manual")
        return {
            "success": True,
            "message": f"浏览器截屏完成",
            "path": shot["path"],
            "url": page.url,
            "title": page.title(),
        }

    def _read(self, page, params: dict) -> dict:
        selector = params.get("selector", "body")
        try:
            element = page.query_selector(selector)
            if not element:
                return {"success": False, "error": f"未找到元素: {selector}"}
            text = element.inner_text()
            # 截断过长内容
            if len(text) > 3000:
                text = text[:3000] + f"\n... (共 {len(text)} 字符，已截断)"
            return {"success": True, "content": text, "url": page.url}
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}

    def _scroll(self, page, params: dict) -> dict:
        direction = params.get("direction", "down")
        amount = params.get("amount", 500)
        if direction == "down":
            page.mouse.wheel(0, amount)
        elif direction == "up":
            page.mouse.wheel(0, -amount)
        time.sleep(0.3)
        shot = _take_screenshot(page, "scroll")
        return {"success": True, "message": f"已向{direction}滚动", "screenshot": shot["path"]}

    def _search(self, page, params: dict) -> dict:
        """便捷搜索：打开搜索引擎并输入关键词"""
        query = params.get("query", "")
        engine = params.get("engine", "google")
        if not query:
            return {"success": False, "error": "缺少 query 参数"}

        search_urls = {
            "google": f"https://www.google.com/search?q={query}",
            "bing": f"https://www.bing.com/search?q={query}",
            "baidu": f"https://www.baidu.com/s?wd={query}",
            "duckduckgo": f"https://duckduckgo.com/?q={query}",
        }
        url = search_urls.get(engine, search_urls["google"])

        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1.5)
        shot = _take_screenshot(page, "search")
        title = page.title()
        return {
            "success": True,
            "message": f"搜索完成: {query} ({engine})",
            "url": page.url,
            "title": title,
            "screenshot": shot["path"],
        }
