"""
LocalMindDesk — FileTool
文件系统操作工具：read/write/edit/append/list/delete/copy/move/mkdir
新增：read 支持 start_line/end_line 行号范围
"""
import os
import shutil
from app.tools.base import BaseTool, ToolContext

# 每个 action 的危险等级
_DANGER = {
    "read": "safe", "list": "safe", "mkdir": "safe",
    "write": "moderate", "edit": "moderate", "append": "moderate",
    "copy": "moderate", "move": "moderate",
    "delete": "critical",
}


class FileTool(BaseTool):
    @property
    def name(self) -> str:
        return "file_op"

    @property
    def description(self) -> str:
        return "文件系统操作（读取、写入、编辑、删除、复制、移动）"

    @property
    def danger_level(self) -> str:
        return "moderate"

    def get_danger_level(self, params: dict) -> str:
        action = params.get("action", "")
        return _DANGER.get(action, "critical")

    def is_read_only(self, params: dict) -> bool:
        return params.get("action") in ("read", "list")

    def is_destructive(self, params: dict) -> bool:
        return params.get("action") == "delete"

    def check_permissions(self, params: dict, ctx: ToolContext = None) -> dict:
        action = params.get("action", "")
        level = self.get_danger_level(params)
        reason = ""
        if action == "delete":
            reason = f"删除操作: {params.get('source', params.get('path', ''))}"
        return {"level": level, "reason": reason, "blocked": False}

    def describe_action(self, params: dict) -> str:
        action = params.get("action", "")
        src = params.get("source", params.get("path", ""))
        dst = params.get("destination", "")
        if action == "delete":
            return f"删除: {src}"
        elif action in ("move", "copy"):
            return f"{action}: {src} → {dst}"
        elif action == "write":
            return f"写入: {src}"
        elif action == "edit":
            return f"编辑: {src}"
        elif action == "append":
            return f"追加到: {src}"
        return f"文件操作 ({action}): {src}"

    def execute(self, params: dict, ctx: ToolContext = None) -> dict:
        action = params.get("action", "")
        source = params.get("source", params.get("path", ""))
        destination = params.get("destination", "")
        content = params.get("content", "")
        target = source

        try:
            if action == "read":
                return self._read(target, params)
            elif action == "list":
                return self._list(target)
            elif action == "write":
                return self._write(target, content)
            elif action == "copy":
                return self._copy(source, destination)
            elif action == "move":
                return self._move(source, destination)
            elif action == "edit":
                return self._edit(target, content, params)
            elif action == "append":
                return self._append(target, content)
            elif action == "delete":
                return self._delete(target)
            elif action == "mkdir":
                return self._mkdir(target)
            else:
                return {"success": False, "error": f"未知操作: {action}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ---- 具体操作实现 ----

    def _read(self, target: str, params: dict) -> dict:
        if not os.path.exists(target):
            return {"success": False, "error": f"文件不存在: {target}"}

        start_line = params.get("start_line", 0)
        end_line = params.get("end_line", 0)

        with open(target, "r", encoding="utf-8", errors="replace") as f:
            if start_line and start_line > 0:
                # 按行号范围读取（新增功能）
                lines = f.readlines()
                total = len(lines)
                s = max(0, start_line - 1)  # 转 0-indexed
                e = min(total, end_line) if end_line and end_line > 0 else total
                selected = lines[s:e]
                # 带行号输出
                numbered = [f"{i+s+1}: {line.rstrip()}" for i, line in enumerate(selected)]
                data = "\n".join(numbered)
                return {
                    "success": True,
                    "content": data,
                    "total_lines": total,
                    "showing": f"{s+1}-{e}",
                    "size": os.path.getsize(target),
                }
            else:
                data = f.read(50000)
                return {"success": True, "content": data, "size": os.path.getsize(target)}

    def _list(self, target: str) -> dict:
        if not os.path.isdir(target):
            return {"success": False, "error": f"目录不存在: {target}"}
        entries = []
        for item in os.listdir(target):
            full = os.path.join(target, item)
            entries.append({
                "name": item,
                "is_dir": os.path.isdir(full),
                "size": os.path.getsize(full) if os.path.isfile(full) else 0,
            })
        return {"success": True, "entries": entries, "count": len(entries)}

    def _write(self, target: str, content: str) -> dict:
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "message": f"已写入 {target}"}

    def _copy(self, source: str, destination: str) -> dict:
        if os.path.isdir(source):
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
            shutil.copy2(source, destination)
        return {"success": True, "message": f"已复制 → {destination}"}

    def _move(self, source: str, destination: str) -> dict:
        os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
        shutil.move(source, destination)
        return {"success": True, "message": f"已移动 → {destination}"}

    def _edit(self, target: str, content: str, params: dict) -> dict:
        if not os.path.exists(target):
            return {"success": False, "error": f"文件不存在: {target}"}
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        # 按行编辑
        line_num = params.get("line", 0)
        if line_num and line_num > 0:
            idx = int(line_num) - 1
            if idx < 0 or idx >= len(lines):
                return {"success": False, "error": f"行号 {line_num} 超出范围（共 {len(lines)} 行）"}
            old_line = lines[idx].rstrip('\n')
            lines[idx] = content + '\n'
            with open(target, "w", encoding="utf-8") as f:
                f.writelines(lines)
            return {"success": True, "message": f"已修改第 {line_num} 行: {old_line!r} → {content!r}"}

        # 搜索替换
        find_str = params.get("find", "")
        replace_str = params.get("replace", "")
        if find_str:
            full_text = "".join(lines)
            count = full_text.count(find_str)
            if count == 0:
                return {"success": False, "error": f"未找到匹配内容: {find_str!r}"}
            new_text = full_text.replace(find_str, replace_str)
            with open(target, "w", encoding="utf-8") as f:
                f.write(new_text)
            return {"success": True, "message": f"已替换 {count} 处: {find_str!r} → {replace_str!r}"}

        return {"success": False, "error": "edit 需要指定 line 或 find 参数"}

    def _append(self, target: str, content: str) -> dict:
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "message": f"已追加内容到 {target}"}

    def _delete(self, target: str) -> dict:
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
        return {"success": True, "message": f"已删除 {target}"}

    def _mkdir(self, target: str) -> dict:
        os.makedirs(target, exist_ok=True)
        return {"success": True, "message": f"已创建目录 {target}"}
