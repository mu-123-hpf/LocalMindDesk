"""
LocalMindDesk — 联网搜索工具
DuckDuckGo HTML 版 + Bing 兜底
"""
import re
import httpx

def web_search(keyword: str) -> str:
    """搜索并返回格式化结果"""
    print(f"[搜索] 关键词: {keyword}")

    result = _search_duckduckgo(keyword)
    if not result:
        result = _search_bing(keyword)

    if not result:
        return "搜索引擎未能提取到有效结果，请稍后重试。"

    print(f"[搜索] 返回 {len(result)} 条结果")
    return result

def _search_duckduckgo(keyword: str) -> str:
    """DuckDuckGo HTML 版搜索"""
    try:
        client = httpx.Client(timeout=15, follow_redirects=True)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        }
        resp = client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": keyword},
            headers=headers,
        )
        if resp.status_code != 200:
            return ""

        body = resp.text
        snippets = re.findall(r'<a class="result__snippet"[^>]*>([\s\S]*?)</a>', body, re.I)

        result = ""
        count = 0
        for s in snippets:
            clean = re.sub(r'<[^>]+>', '', s).strip()
            clean = re.sub(r'\s+', ' ', clean)
            if len(clean) > 20:
                count += 1
                result += f"资料{count}: {clean}\n"
            if count >= 5:
                break
        return result
    except Exception as e:
        print(f"[搜索] DuckDuckGo 失败: {e}")
        return ""

def _search_bing(keyword: str) -> str:
    """Bing 直连兜底"""
    try:
        client = httpx.Client(timeout=15, follow_redirects=True)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        }
        resp = client.get(
            f"https://www.bing.com/search?q={httpx.URL(keyword)}",
            headers=headers,
        )
        if resp.status_code != 200:
            return ""

        body = resp.text
        snippets = re.findall(r'<div class="b_caption">([\s\S]*?)</div>', body, re.I)

        result = ""
        count = 0
        for s in snippets:
            clean = re.sub(r'<[^>]+>', '', s).strip()
            clean = re.sub(r'\s+', ' ', clean)
            if len(clean) > 20:
                count += 1
                result += f"资料{count}: {clean}\n"
            if count >= 5:
                break
        return result
    except Exception as e:
        print(f"[搜索] Bing 失败: {e}")
        return ""
