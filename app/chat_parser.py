"""
LocalMindDesk — 聊天记录解析器（多格式版）

支持格式:
1. txt — WeChatMsg / WechatExporter / 留痕 / 通用时间戳格式
2. html/htm — WeChatMsg / PyWxDump 导出的 HTML 聊天页面
3. json — 留痕 / 结构化聊天数据 (array or {messages:[...]})
4. csv — WeChatMsg 导出的 CSV
5. mht — QQ 合并转发的网页格式
6. 纯文本 — 手动粘贴的聊天记录

参考: https://github.com/1544501967/friend-skill/blob/main/tools/wechat_parser.py
"""
import re
import os
import json
import csv
import io
from typing import List, Optional
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ChatMessage:
    """单条聊天消息"""
    timestamp: str = ""
    sender: str = ""
    content: str = ""
    is_target: bool = False  # 是否是目标人物发送的


@dataclass
class ParseResult:
    """解析结果"""
    messages: List[ChatMessage] = field(default_factory=list)
    target_name: str = ""
    total_messages: int = 0
    target_messages: int = 0
    user_messages: int = 0
    date_range: str = ""
    raw_text: str = ""  # 原始文本（供 LLM 分析用）
    format_detected: str = ""  # 检测到的格式

    def target_text(self) -> str:
        """提取目标人物的所有消息文本"""
        return "\n".join(
            m.content for m in self.messages if m.is_target and m.content.strip()
        )

    def summary_text(self, max_chars: int = 8000) -> str:
        """生成适合 LLM 分析的摘要文本"""
        lines = []
        for m in self.messages:
            tag = f"[{m.sender}]" if m.sender else ""
            lines.append(f"{m.timestamp} {tag} {m.content}")
        text = "\n".join(lines)
        if len(text) > max_chars:
            # 取前后各一半
            half = max_chars // 2
            text = text[:half] + "\n\n...(中间省略)...\n\n" + text[-half:]
        return text


# ============================================================
#  格式自动检测
# ============================================================

def detect_format(file_path: str) -> str:
    """自动检测文件格式，返回格式标识符"""
    ext = Path(file_path).suffix.lower()

    if ext == '.json':
        return 'json'
    elif ext == '.csv':
        return 'csv'
    elif ext in ('.html', '.htm'):
        return 'html'
    elif ext == '.mht':
        return 'mht'
    elif ext == '.txt':
        # 尝试区分 WeChatMsg txt 和纯文本
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                first_lines = f.read(2000)
        except Exception:
            return 'plaintext'
        # WeChatMsg 格式通常有时间戳模式
        if re.search(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', first_lines):
            return 'wechatmsg_txt'
        # WechatExporter 格式: "2024-01-15 20:30 小美: xxx"
        if re.search(r'\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}', first_lines):
            return 'wechat_exporter'
        return 'plaintext'
    else:
        return 'plaintext'


def detect_format_from_content(text: str, filename: str = "") -> str:
    """从文本内容检测格式（用于前端直传文本场景）"""
    ext = Path(filename).suffix.lower() if filename else ""

    if ext == '.json' or (text.strip().startswith('{') or text.strip().startswith('[')):
        try:
            json.loads(text)
            return 'json'
        except Exception:
            pass

    if ext in ('.html', '.htm') or '<html' in text.lower()[:500]:
        return 'html'

    if ext == '.csv':
        return 'csv'

    if ext == '.mht' or 'Content-Type: multipart' in text[:500]:
        return 'mht'

    # 时间戳检测
    if re.search(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', text[:2000]):
        return 'wechatmsg_txt'
    if re.search(r'\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}', text[:2000]):
        return 'wechat_exporter'

    return 'plaintext'


# ============================================================
#  各格式解析器
# ============================================================

class ChatParser:
    """聊天记录解析器（多格式）"""

    # WechatExporter 格式: "2024-01-15 20:30:15 小美: 你在干嘛"
    _WECHAT_PATTERN = re.compile(
        r'^(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}(?::\d{2})?)\s+(.+?)[:：]\s*(.*)$'
    )

    # WeChatMsg 格式: "2024-01-15 20:30:45 张三\n今天好累啊"
    _WECHATMSG_PATTERN = re.compile(
        r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(.+)$'
    )

    # 简化格式: "小美: 你在干嘛" 或 "小美：你在干嘛"
    _SIMPLE_PATTERN = re.compile(
        r'^(.+?)[:：]\s*(.+)$'
    )

    # HTML 中的消息块模式 (WeChatMsg/PyWxDump 导出)
    _HTML_MSG_PATTERN = re.compile(
        r'<div[^>]*class="[^"]*(?:message|msg|chat-item|bubble)[^"]*"[^>]*>(.*?)</div>',
        re.DOTALL | re.IGNORECASE
    )

    _HTML_SENDER_PATTERN = re.compile(
        r'<(?:span|div|p)[^>]*class="[^"]*(?:sender|nickname|name|username)[^"]*"[^>]*>(.*?)</(?:span|div|p)>',
        re.DOTALL | re.IGNORECASE
    )

    _HTML_CONTENT_PATTERN = re.compile(
        r'<(?:span|div|p)[^>]*class="[^"]*(?:content|text|msg-text|message-text)[^"]*"[^>]*>(.*?)</(?:span|div|p)>',
        re.DOTALL | re.IGNORECASE
    )

    _HTML_TIME_PATTERN = re.compile(
        r'<(?:span|div)[^>]*class="[^"]*(?:time|timestamp|date)[^"]*"[^>]*>(.*?)</(?:span|div)>',
        re.DOTALL | re.IGNORECASE
    )

    def parse(self, text: str, target_name: str = "",
              filename: str = "") -> ParseResult:
        """
        解析聊天记录文本（统一入口）

        Args:
            text: 聊天记录文本
            target_name: 目标人物名称
            filename: 原始文件名（用于格式检测）

        Returns:
            ParseResult
        """
        if not text or not text.strip():
            return ParseResult(raw_text=text)

        # 自动检测格式
        fmt = detect_format_from_content(text, filename)

        # 根据格式分发
        if fmt == 'json':
            result = self._parse_json(text, target_name)
        elif fmt == 'html':
            result = self._parse_html(text, target_name)
        elif fmt == 'csv':
            result = self._parse_csv(text, target_name)
        elif fmt == 'mht':
            result = self._parse_mht(text, target_name)
        elif fmt == 'wechatmsg_txt':
            result = self._parse_wechatmsg_txt(text, target_name)
        elif fmt == 'wechat_exporter':
            lines = text.strip().split("\n")
            result = self._try_wechat_format(lines, target_name)
        else:
            # 尝试多种格式
            lines = text.strip().split("\n")
            result = self._try_wechat_format(lines, target_name)
            if result.total_messages <= 3:
                result = self._try_simple_format(lines, target_name)
            if result.total_messages <= 3:
                result = ParseResult(
                    raw_text=text,
                    total_messages=0,
                    target_name=target_name,
                    format_detected='plaintext',
                )
                return result

        result.format_detected = fmt
        return result

    def parse_file(self, filepath: str, target_name: str = "",
                   encoding: str = "utf-8") -> ParseResult:
        """从文件解析"""
        fmt = detect_format(filepath)
        filename = os.path.basename(filepath)

        try:
            with open(filepath, "r", encoding=encoding) as f:
                text = f.read()
        except UnicodeDecodeError:
            try:
                with open(filepath, "r", encoding="gbk") as f:
                    text = f.read()
            except UnicodeDecodeError:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()

        result = self.parse(text, target_name, filename)
        result.format_detected = fmt
        return result

    # ── JSON 解析 ────────────────────────────────────────────

    def _parse_json(self, text: str, target: str) -> ParseResult:
        """
        解析 JSON 格式的聊天记录

        支持结构:
          - 数组: [{sender, content, time/timestamp}, ...]
          - 对象: {messages: [...]} 或 {data: [...]}
          - 留痕格式: {messages: [{from, text, time}]}
        """
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return ParseResult(raw_text=text, target_name=target,
                               format_detected='json')

        # 提取消息列表
        if isinstance(data, list):
            msg_list = data
        elif isinstance(data, dict):
            msg_list = (data.get('messages')
                        or data.get('data')
                        or data.get('records')
                        or data.get('chatMessages')
                        or [])
        else:
            return ParseResult(raw_text=text, target_name=target)

        messages = []
        for item in msg_list:
            if not isinstance(item, dict):
                continue
            sender = (item.get('sender')
                      or item.get('nickname')
                      or item.get('from')
                      or item.get('name')
                      or item.get('talker')
                      or '')
            content = (item.get('content')
                       or item.get('message')
                       or item.get('text')
                       or item.get('msg')
                       or '')
            timestamp = (item.get('time')
                         or item.get('timestamp')
                         or item.get('date')
                         or item.get('createTime')
                         or '')
            # timestamp 可能是数字（unix 时间戳）
            if isinstance(timestamp, (int, float)) and timestamp > 1e9:
                from datetime import datetime
                try:
                    timestamp = datetime.fromtimestamp(timestamp).strftime(
                        '%Y-%m-%d %H:%M:%S')
                except Exception:
                    timestamp = str(timestamp)

            if not content:
                continue

            is_target = self._is_target(str(sender), target) if target else False
            messages.append(ChatMessage(
                timestamp=str(timestamp),
                sender=str(sender).strip(),
                content=str(content).strip(),
                is_target=is_target,
            ))

        if not messages:
            return ParseResult(raw_text=text, target_name=target)

        if not target:
            target = self._infer_target(messages)

        return self._build_result(messages, target)

    # ── HTML 解析 ────────────────────────────────────────────

    def _parse_html(self, text: str, target: str) -> ParseResult:
        """
        解析 HTML 格式的聊天记录

        支持:
          - WeChatMsg 导出 HTML
          - PyWxDump 导出 HTML
          - 通用聊天 HTML（带 class 标识的消息块）
        """
        # 策略 1: 尝试结构化 HTML 解析
        messages = self._extract_html_structured(text, target)

        # 策略 2: 如果结构化失败，剥离 HTML 标签后按文本解析
        if len(messages) < 3:
            clean_text = self._strip_html(text)
            lines = clean_text.strip().split("\n")

            result = self._try_wechat_format(lines, target)
            if result.total_messages > 3:
                return result

            # WeChatMsg txt 模式
            result = self._parse_wechatmsg_txt(clean_text, target)
            if result.total_messages > 3:
                return result

            result = self._try_simple_format(lines, target)
            if result.total_messages > 3:
                return result

            # 最终回退：返回清理后的纯文本
            return ParseResult(
                raw_text=clean_text[:50000],
                target_name=target,
                total_messages=0,
                format_detected='html',
            )

        if not target:
            target = self._infer_target(messages)

        return self._build_result(messages, target)

    def _extract_html_structured(self, html: str, target: str) -> list:
        """从 HTML 中提取结构化消息"""
        messages = []

        # 查找所有时间戳
        times = self._HTML_TIME_PATTERN.findall(html)
        senders = self._HTML_SENDER_PATTERN.findall(html)
        contents = self._HTML_CONTENT_PATTERN.findall(html)

        # 如果三者数量对齐，直接配对
        if contents and len(senders) == len(contents):
            for i, content in enumerate(contents):
                clean_content = self._strip_html(content).strip()
                if not clean_content:
                    continue
                sender = self._strip_html(senders[i]).strip() if i < len(senders) else ""
                ts = self._strip_html(times[i]).strip() if i < len(times) else ""
                is_target = self._is_target(sender, target) if target else False
                messages.append(ChatMessage(
                    timestamp=ts, sender=sender,
                    content=clean_content, is_target=is_target,
                ))

        return messages

    def _strip_html(self, html: str) -> str:
        """清除 HTML 标签，保留纯文本"""
        # 替换 <br> 为换行
        text = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
        # 替换 </p> </div> 为换行
        text = re.sub(r'</(?:p|div|li|tr)>', '\n', text, flags=re.IGNORECASE)
        # 删除所有标签
        text = re.sub(r'<[^>]+>', '', text)
        # 解码 HTML 实体
        text = text.replace('&nbsp;', ' ').replace('&lt;', '<')
        text = text.replace('&gt;', '>').replace('&amp;', '&')
        text = text.replace('&quot;', '"').replace('&#39;', "'")
        # 压缩多余空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    # ── CSV 解析 ──────────────────────────────────────────────

    def _parse_csv(self, text: str, target: str) -> ParseResult:
        """
        解析 CSV 格式的聊天记录

        支持列名: sender/nickname/from, content/message/text, time/timestamp
        """
        messages = []
        try:
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                sender = (row.get('sender') or row.get('nickname')
                          or row.get('from') or row.get('发送者')
                          or row.get('昵称') or '')
                content = (row.get('content') or row.get('message')
                           or row.get('text') or row.get('内容')
                           or row.get('消息') or '')
                timestamp = (row.get('time') or row.get('timestamp')
                             or row.get('date') or row.get('时间') or '')

                if not content:
                    continue

                is_target = self._is_target(sender, target) if target else False
                messages.append(ChatMessage(
                    timestamp=str(timestamp).strip(),
                    sender=sender.strip(),
                    content=content.strip(),
                    is_target=is_target,
                ))
        except Exception:
            return ParseResult(raw_text=text, target_name=target)

        if not messages:
            return ParseResult(raw_text=text, target_name=target)

        if not target:
            target = self._infer_target(messages)

        return self._build_result(messages, target)

    # ── MHT 解析 ──────────────────────────────────────────────

    def _parse_mht(self, text: str, target: str) -> ParseResult:
        """解析 QQ 的 MHT 格式（合并转发的网页格式）"""
        clean_text = self._strip_html(text)

        # 尝试按文本格式解析
        lines = clean_text.strip().split("\n")
        result = self._try_wechat_format(lines, target)
        if result.total_messages > 3:
            return result

        result = self._try_simple_format(lines, target)
        if result.total_messages > 3:
            return result

        return ParseResult(
            raw_text=clean_text[:50000],
            target_name=target,
            total_messages=0,
            format_detected='mht',
        )

    # ── WeChatMsg TXT 格式 ────────────────────────────────────

    def _parse_wechatmsg_txt(self, text: str, target: str) -> ParseResult:
        """
        解析 WeChatMsg 导出的 txt 格式

        格式:
        2024-01-15 20:30:45 张三
        今天好累啊

        2024-01-15 20:31:02 我
        怎么了？
        """
        messages = []
        current_msg = None

        for line in text.split('\n'):
            line_stripped = line.rstrip('\n')
            match = self._WECHATMSG_PATTERN.match(line_stripped.strip())
            if match:
                if current_msg:
                    messages.append(current_msg)
                timestamp, sender = match.groups()
                is_target = self._is_target(sender.strip(), target) if target else False
                current_msg = ChatMessage(
                    timestamp=timestamp,
                    sender=sender.strip(),
                    content='',
                    is_target=is_target,
                )
            elif current_msg and line_stripped.strip():
                if current_msg.content:
                    current_msg.content += '\n'
                current_msg.content += line_stripped.strip()

        if current_msg:
            messages.append(current_msg)

        if not messages:
            return ParseResult(raw_text=text, target_name=target)

        if not target:
            target = self._infer_target(messages)

        return self._build_result(messages, target)

    # ── 原有格式兼容 ──────────────────────────────────────────

    def _try_wechat_format(self, lines: list, target: str) -> ParseResult:
        """尝试 WechatExporter 格式解析"""
        messages = []
        current_msg = None

        for line in lines:
            match = self._WECHAT_PATTERN.match(line.strip())
            if match:
                if current_msg:
                    messages.append(current_msg)
                ts, sender, content = match.groups()
                is_target = self._is_target(sender, target)
                current_msg = ChatMessage(
                    timestamp=ts,
                    sender=sender.strip(),
                    content=content.strip(),
                    is_target=is_target,
                )
            elif current_msg and line.strip():
                # 多行消息的后续行
                current_msg.content += "\n" + line.strip()

        if current_msg:
            messages.append(current_msg)

        if not messages:
            return ParseResult()

        # 自动推断 target_name
        if not target:
            target = self._infer_target(messages)

        return self._build_result(messages, target)

    def _try_simple_format(self, lines: list, target: str) -> ParseResult:
        """尝试简单的 "名字: 内容" 格式"""
        messages = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            match = self._SIMPLE_PATTERN.match(line)
            if match:
                sender, content = match.groups()
                sender = sender.strip()
                # 过滤掉太长的 sender（可能不是名字）
                if len(sender) > 20:
                    continue
                is_target = self._is_target(sender, target)
                messages.append(ChatMessage(
                    sender=sender,
                    content=content.strip(),
                    is_target=is_target,
                ))

        if not messages:
            return ParseResult()

        if not target:
            target = self._infer_target(messages)

        return self._build_result(messages, target)

    # ── 工具方法 ──────────────────────────────────────────────

    def _is_target(self, sender: str, target: str) -> bool:
        """判断是否是目标人物"""
        if not target:
            return False
        return target.lower() in sender.lower() or sender.lower() in target.lower()

    def _infer_target(self, messages: list) -> str:
        """推断目标人物（消息最多的那个人）"""
        from collections import Counter
        senders = Counter(m.sender for m in messages if m.sender)
        if len(senders) >= 2:
            # 假设消息第二多的是目标（最多的通常是"我"）
            top2 = senders.most_common(2)
            return top2[1][0]
        elif senders:
            return senders.most_common(1)[0][0]
        return ""

    def _build_result(self, messages: list, target: str) -> ParseResult:
        """构建解析结果"""
        # 重新标记 is_target
        for m in messages:
            m.is_target = self._is_target(m.sender, target)

        target_msgs = [m for m in messages if m.is_target]
        user_msgs = [m for m in messages if not m.is_target]

        dates = [m.timestamp for m in messages if m.timestamp]
        date_range = ""
        if dates:
            date_range = f"{dates[0]} ~ {dates[-1]}"

        return ParseResult(
            messages=messages,
            target_name=target,
            total_messages=len(messages),
            target_messages=len(target_msgs),
            user_messages=len(user_msgs),
            date_range=date_range,
            raw_text="\n".join(
                f"{m.timestamp} {m.sender}: {m.content}" for m in messages
            ),
        )


# ============================================================
#  便捷函数
# ============================================================

def get_supported_extensions() -> list:
    """返回支持的文件扩展名列表"""
    return ['.txt', '.html', '.htm', '.json', '.csv', '.mht', '.log']


def get_supported_accept_string() -> str:
    """返回 HTML input[accept] 属性值"""
    return '.txt,.html,.htm,.json,.csv,.mht,.log'
