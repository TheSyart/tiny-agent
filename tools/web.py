"""Built-in tools for web operations"""

import asyncio
import aiohttp
from typing import Optional
from .base import tool


@tool(is_concurrency_safe=True)
async def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the web for information using DuckDuckGo.

    Args:
        query: The search query
        max_results: Maximum number of results to return
    """
    try:
        from duckduckgo_search import DDGS

        loop = asyncio.get_event_loop()

        def _sync_search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))

        results = await loop.run_in_executor(None, _sync_search)

        if not results:
            return f"未找到关于「{query}」的结果"

        lines = []
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            lines.append(f"**{title}**\n{body}\n{href}")

        return "\n\n---\n\n".join(lines)

    except ImportError:
        return (
            "web_search 依赖未安装，请运行: pip install duckduckgo-search\n"
            "安装后重启服务即可使用搜索功能。"
        )
    except Exception as e:
        return f"Search error: {str(e)}"


@tool(is_concurrency_safe=True)
async def web_fetch(url: str, selector: Optional[str] = None) -> str:
    """
    Fetch and extract content from a web page

    Args:
        url: The URL to fetch
        selector: Optional CSS selector to extract specific content
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; TinyAgent/1.0)"
            }

            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    return f"Fetch failed with status {response.status}"

                html = await response.text()

        # Simple text extraction
        text = _extract_text_from_html(html)

        if selector:
            # TODO: Implement CSS selector extraction
            pass

        # Truncate if too long
        max_length = 10000
        if len(text) > max_length:
            text = text[:max_length] + "\n\n... (content truncated)"

        return text

    except aiohttp.ClientError as e:
        return f"Fetch error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


def _extract_text_from_html(html: str) -> str:
    """Extract readable text from HTML"""
    import re

    # Remove scripts and styles
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

    # Remove comments
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)

    # Replace common block elements with newlines
    for tag in ['p', 'div', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'tr']:
        html = re.sub(f'<{tag}[^>]*>', '\n', html, flags=re.IGNORECASE)
        html = re.sub(f'</{tag}>', '\n', html, flags=re.IGNORECASE)

    # Remove remaining tags
    html = re.sub(r'<[^>]+>', '', html)

    # Decode HTML entities
    import html as html_module
    text = html_module.unescape(html)

    # Clean up whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    text = text.strip()

    return text