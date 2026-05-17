"""tools/web.py — web_fetch + web_search 工具。

对齐 OpenClaw web fetch/search 能力。
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from tools.registry import tool, ToolManifest, ToolResult, ToolParam, ToolContext
from tools.file import _workspace_candidate_path

# ── 常量 ─────────────────────────────────────────────────────────────────────
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
MAX_FETCH_CHARS = 50000
MAX_FETCH_TIMEOUT = 30
MAX_SEARCH_RESULTS = 10
SEARCH_TIMEOUT = 15


# ── 共享 HTTP 客户端 ─────────────────────────────────────────────────────────
_http_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        import os
        limits = httpx.Limits(max_connections=5, max_keepalive_connections=2)
        proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(MAX_FETCH_TIMEOUT),
            limits=limits,
            follow_redirects=True,
            headers={"User-Agent": DEFAULT_UA},
            proxy=proxy,
        )
    return _http_client


# ── HTML → 纯文本 ────────────────────────────────────────────────────────────


def _html_to_text(html: str, max_chars: int = MAX_FETCH_CHARS) -> str:
    """将 HTML 转为可读纯文本。"""
    # 移除 script/style
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # 移除标签
    text = re.sub(r"<[^>]+>", " ", html)
    # 处理实体
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # 压缩空白
    text = re.sub(r"\s+", " ", text).strip()
    # 去重空行
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars] + f"\n...(截断，原文共 {len(result)} 字符)"
    return result


# ── web.fetch ────────────────────────────────────────────────────────────────


@tool(ToolManifest(
    name="web.fetch",
    description=(
        "获取 Web 页面内容。可用于阅读在线文档、API 文档、论文、博客等。"
        "自动将 HTML 转为纯文本。"
    ),
    progress_category="io",
    params=[
        ToolParam("url", "string", "页面 URL", required=True),
        ToolParam("max_chars", "number", "最大返回字符数（默认 50000）", required=False),
    ],
))
async def web_fetch(params: dict[str, Any], ctx: ToolContext) -> ToolResult:
    url = (params.get("url") or "").strip()
    if not url:
        return ToolResult(summary="URL 不能为空", error="EmptyUrl", skipped=True)

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return ToolResult(summary=f"不支持的协议: {parsed.scheme}", error="BadScheme", skipped=True)

    max_chars = min(int(params.get("max_chars", MAX_FETCH_CHARS)), MAX_FETCH_CHARS)

    try:
        client = await _get_client()
        resp = await client.get(url)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        text: str

        if "text/html" in content_type:
            text = _html_to_text(resp.text, max_chars)
        elif "text/" in content_type or "application/json" in content_type:
            text = resp.text[:max_chars]
            if len(resp.text) > max_chars:
                text += f"\n...(截断，原文共 {len(resp.text)} 字符)"
        else:
            return ToolResult(
                summary=f"不支持的内容类型: {content_type}",
                error="UnsupportedContentType",
                skipped=True,
            )

        return ToolResult(
            summary=f"获取成功: {url}\n状态: {resp.status_code}  大小: {len(text)} 字符",
            resource_key=url,
            evidence=text[:200],
            metadata={
                "url": url,
                "status": resp.status_code,
                "chars": len(text),
                "content_type": content_type,
            },
            state_delta={"fetched": url, "chars": len(text)},
        )
    except httpx.HTTPStatusError as e:
        return ToolResult(summary=f"HTTP {e.response.status_code}: {url}", error="HttpError")
    except httpx.TimeoutException:
        return ToolResult(summary=f"请求超时: {url}", error="Timeout")
    except Exception as e:
        return ToolResult(summary=f"获取失败: {type(e).__name__}", error="FetchError")


# ── web.search ───────────────────────────────────────────────────────────────


@tool(ToolManifest(
    name="web.search",
    description=(
        "搜索 Web 信息。使用 DuckDuckGo 匿名搜索。"
        "返回标题、摘要和 URL。适合查找文档、论文、技术问题等。"
    ),
    progress_category="io",
    params=[
        ToolParam("query", "string", "搜索关键词", required=True),
        ToolParam("max_results", "number", "最大结果数（默认 10）", required=False),
    ],
))
async def web_search(params: dict[str, Any], ctx: ToolContext) -> ToolResult:
    query = (params.get("query") or "").strip()
    if not query:
        return ToolResult(summary="搜索关键词不能为空", error="EmptyQuery", skipped=True)

    max_results = min(int(params.get("max_results", MAX_SEARCH_RESULTS)), MAX_SEARCH_RESULTS)

    try:
        client = await _get_client()
        # DuckDuckGo HTML 搜索（无需 API key）
        search_url = "https://html.duckduckgo.com/html/"
        resp = await client.post(search_url, data={"q": query})
        resp.raise_for_status()

        # 解析搜索结果
        results: list[dict[str, str]] = []
        for match in re.finditer(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            resp.text,
            re.DOTALL,
        ):
            if len(results) >= max_results:
                break
            url = match.group(1).strip()
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()
            if url and title:
                results.append({"title": title, "url": url, "snippet": snippet})

        if not results:
            return ToolResult(
                summary=f"搜索无结果: {query}",
                evidence="",
                metadata={"query": query, "results": 0},
            )

        summary_lines = [f"搜索 '{query}': {len(results)} 条结果"]
        for i, r in enumerate(results, 1):
            summary_lines.append(f"  [{i}] {r['title']}")
            summary_lines.append(f"      {r['url']}")
            if r["snippet"]:
                summary_lines.append(f"      {r['snippet'][:120]}")

        return ToolResult(
            summary="\n".join(summary_lines),
            resource_key=f"search:{hashlib.md5(query.encode()).hexdigest()[:12]}",
            evidence=summary_lines[-1] if len(summary_lines) > 1 else "",
            metadata={"query": query, "results": len(results)},
            state_delta={"searched": query, "results": len(results)},
        )
    except Exception as e:
        return ToolResult(summary=f"搜索失败: {type(e).__name__}", error="SearchError")
