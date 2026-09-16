"""Free web search helpers (no API keys): Brave → DuckDuckGo → Bing."""
from __future__ import annotations

import html as html_lib
import logging
import re
from urllib.parse import quote_plus, unquote

import httpx

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


def _uniq(items: list[str], limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        u = (raw or "").strip().split("#")[0]
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= limit:
            break
    return out


async def web_links(client: httpx.AsyncClient, query: str, limit: int = 12) -> list[str]:
    if not (query or "").strip():
        return []
    links: list[str] = []
    try:
        resp = await client.get(
            "https://search.brave.com/search",
            params={"q": query, "source": "web"},
            headers=HEADERS,
            timeout=18.0,
        )
        for m in re.finditer(r'href="(https?://[^"]+)"', resp.text or ""):
            href = html_lib.unescape(m.group(1)).split("&")[0]
            low = href.lower()
            if any(x in low for x in ("brave.com", "brave.cloud", "youtube.com")):
                continue
            links.append(href)
            if len(links) >= limit * 2:
                break
    except Exception as exc:
        log.info("brave web failed: %s", exc)
    if len(links) >= limit:
        return _uniq(links, limit)
    try:
        resp = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=HEADERS,
            timeout=18.0,
        )
        if resp.status_code < 400 and "anomaly" not in (resp.text or "").lower():
            for raw in re.findall(r"uddg=([^&\"']+)", resp.text or ""):
                href = unquote(raw)
                if href.startswith("http") and "duckduckgo." not in href.lower():
                    links.append(href.split("&")[0])
    except Exception as exc:
        log.info("ddg web failed: %s", exc)
    if len(links) >= limit:
        return _uniq(links, limit)
    try:
        resp = await client.get(
            f"https://www.bing.com/search?q={quote_plus(query)}&setlang=ru",
            headers=HEADERS,
            timeout=18.0,
        )
        if resp.status_code < 400:
            for m in re.finditer(r'href="(https?://[^"]+)"', resp.text or ""):
                href = html_lib.unescape(m.group(1)).split("&")[0]
                if "bing.com" in href or "microsoft.com" in href:
                    continue
                links.append(href)
    except Exception as exc:
        log.info("bing web failed: %s", exc)
    return _uniq(links, limit)
