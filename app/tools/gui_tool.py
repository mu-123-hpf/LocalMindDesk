"""
LocalMindDesk — GUITool
GUI 自动化工具：点击、输入、快捷键、截屏
"""
import os
from datetime import datetime
from app.tools.base import BaseTool, ToolContext

# 每个 action 的危险等级
_DANGER = {
    "screenshot": "safe",
    "click": "moderate",
    "type": "moderate",
    "hotkey": "moderate",
}


class GUITool(BaseTool):
    @property
    def name(self) -> str:
        return "gui_action"

    @property
    def description(self) -> str:
        return "GUI 自动化操作（点击、输入、快捷键、截屏）"

    @property
    def danger_level(self) -> str:
        return "moderate"

    def get_danger_level(self, params: dict) -> str:
        action = params.get("action", "")
        return _DANGER.get(action, "moderate")

    def is_read_only(self, params: dict) -> bool:
        return params.get("action") == "screenshot"

    def describe_action(self, params: dict) -> str:
        action = params.get("action", "")
        if action == "click":
            return f"点击 ({params.get('x')}, {params.get('y')})"
        elif action == "type":
            return f"输入: {params.get('text', '')[:30]}"
        elif action == "hotkey":
            return f"按键: {'+'.join(params.get('keys', []))}"
        return f"GUI: {action}"

    def execute(self, params: dict, ctx: ToolContext = None) -> dict:
        action = params.get("action", "")
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.3

            if action == "click":
                pyautogui.click(params.get("x", 0), params.get("y", 0))
                return {"success": True, "message": f"已点击 ({params.get('x', 0)}, {params.get('y', 0)})"}
            elif action == "type":
                text = params.get("text", "")
                if text.isascii():
                    pyautogui.typewrite(text, interval=0.02)
                else:
                    pyautogui.write(text)
                return {"success": True, "message": "已输入文本"}
            elif action == "hotkey":
                keys = params.get("keys", [])
                if keys:
                    pyautogui.hotkey(*keys)
                    return {"success": True, "message": f"已按 {'+'.join(keys)}"}
                return {"success": False, "error": "未指定按键"}
            elif action == "screenshot":
                return self._screenshot()
            else:
                return {"success": False, "error": f"未知 GUI 操作: {action}"}
        except ImportError:
            return {"success": False, "error": "pyautogui 未安装。运行: pip install pyautogui"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _screenshot(self, save_to: str = "") -> dict:
        try:
            import pyautogui
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")

            if save_to and os.path.isdir(save_to):
                # 保存到指定目录
                path = os.path.join(save_to, f"screenshot_{ts}.png")
            else:
                os.makedirs("data/screenshots", exist_ok=True)
                path = f"data/screenshots/screen_{ts}.png"

            img = pyautogui.screenshot()
            img.save(path)
            abs_path = os.path.abspath(path)
            return {"success": True, "message": f"截屏完成，已保存: {abs_path}", "path": abs_path}
        except ImportError:
            return {"success": False, "error": "pyautogui 未安装。运行: pip install pyautogui"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ScreenCaptureTool(BaseTool):
    """独立的截屏工具（screen_capture 别名）"""
    @property
    def name(self) -> str:
        return "screen_capture"

    @property
    def description(self) -> str:
        return "截取当前屏幕"

    @property
    def danger_level(self) -> str:
        return "safe"

    def is_read_only(self, params: dict) -> bool:
        return True

    def describe_action(self, params: dict) -> str:
        save_to = params.get("save_to", "")
        if save_to:
            return f"截屏并保存到 {save_to}"
        return "截屏"

    def execute(self, params: dict, ctx: ToolContext = None) -> dict:
        gui = GUITool()
        save_to = params.get("save_to", "")
        return gui._screenshot(save_to=save_to)
