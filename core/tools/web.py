"""Web search and page fetch — Brave API primary, DuckDuckGo fallback."""

import re
import json
import httpx
from config import CONFIG
from logger import tool_logger
from models import ToolResult, ToolContext
from security import check_for_injection

# Per-session search result cache for result_id lookup
_cache: dict[str, list[dict]] = {}

# Internal URLs to block for fetch
_BLOCKED_URL_PATTERNS = ["169.254.169.254", "localhost", "127.", "10.", "192.168.", "172.1"]


async def tool_search_web(args: dict, ctx: ToolContext) -> ToolResult:
    query = args.get("query", "").strip()
    limit = min(int(args.get("limit", 5)), 10)
    if not query:
        return ToolResult(False, error="query is required")

    tool_logger.info(f"Search: {query}")

    results = None
    if CONFIG.brave_api_key:
        results = await _brave_search(query, limit)

    if results is None:
        results = await _ddg_search(query, limit)

    if results is None:
        return ToolResult(False, error="Search failed (no results)")

    _cache[ctx.session_id] = results

    lines = []
    for i, r in enumerate(results, 1):
        date = f" ({r.get('date', '')})" if r.get("date") else ""
        snippet = (r.get("snippet") or "")[:300]
        lines.append(f"[{i}] {r['title']}{date}\n{r['url']}\n{snippet}")

    return ToolResult(True, output="\n\n".join(lines))


async def tool_fetch_page(args: dict, ctx: ToolContext) -> ToolResult:
    url = args.get("url", "").strip()
    result_id = args.get("result_id")

    if result_id and not url:
        try:
            idx = int(result_id) - 1
            cached = _cache.get(ctx.session_id, [])
            if 0 <= idx < len(cached):
                url = cached[idx]["url"]
            else:
                return ToolResult(False, error=f"Result {result_id} not in cache")
        except (ValueError, TypeError):
            return ToolResult(False, error=f"Invalid result_id: {result_id}")

    if not url:
        return ToolResult(False, error="url or result_id required")

    if any(b in url for b in _BLOCKED_URL_PATTERNS):
        return ToolResult(False, error="🚫 Internal URL blocked")

    tool_logger.info(f"Fetch: {url}")
    try:
        content = None
        # Try Jina reader first (clean markdown)
        jina_url = f"https://r.jina.ai/{url}"
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(jina_url, headers={"Accept": "text/plain"})
            if resp.status_code == 200:
                content = resp.text[:50000]

        if content is None:
            # Fallback: direct fetch + strip HTML tags
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url)
                content = re.sub(r"<[^>]+>", " ", resp.text)
                content = re.sub(r"\s+", " ", content).strip()
                content = content[:50000]

        # Injection check
        if check_for_injection(content):
            return ToolResult(
                True,
                output=content,
                metadata={"injection_warning": True},
            )

        return ToolResult(True, output=content)

    except Exception as e:
        tool_logger.error(f"Fetch error: {e}")
        return ToolResult(False, error=str(e))


async def _brave_search(query: str, limit: int) -> list | None:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": limit},
                headers={"Accept": "application/json", "X-Subscription-Token": CONFIG.brave_api_key},
            )
            if resp.status_code != 200:
                tool_logger.warning(f"Brave API error: {resp.status_code}")
                return None
            data = resp.json()
            results = []
            for r in data.get("web", {}).get("results", [])[:limit]:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("description", ""),
                    "date": r.get("age", ""),
                })
            return results or None
    except Exception as e:
        tool_logger.warning(f"Brave search failed: {e}")
        return None


async def _ddg_search(query: str, limit: int) -> list | None:
    """DuckDuckGo HTML scrape fallback."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            # Use DuckDuckGo instant answers API (no key required)
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; LocalClaw/1.0)",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            if resp.status_code != 200:
                return None

            html = resp.text
            # Extract result blocks: title, url, snippet
            titles = re.findall(r'class="result__a"[^>]*>([^<]+)', html)
            urls = re.findall(r'class="result__url"[^>]*>\s*([^\s<]+)', html)
            snippets = re.findall(r'class="result__snippet"[^>]*>([^<]+)', html)

            results = []
            for i in range(min(limit, len(titles))):
                url = urls[i].strip() if i < len(urls) else ""
                if not url.startswith("http"):
                    url = "https://" + url
                results.append({
                    "title": titles[i].strip(),
                    "url": url,
                    "snippet": snippets[i].strip() if i < len(snippets) else "",
                })
            return results or None
    except Exception as e:
        tool_logger.warning(f"DDG search failed: {e}")
        return None


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for current information. Returns top results with titles, URLs, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Number of results (default 5, max 10)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": "Fetch and read the content of a web page. Pass url or result_id from search_web.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "result_id": {"type": "integer", "description": "Result number from search_web (1-based)"},
                },
            },
        },
    },
]
