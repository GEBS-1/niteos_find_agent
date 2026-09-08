"""Real web search via API keys (not HTML scraping).

Primary: Serper (Google SERP) — SERPER_API_KEY
Fallback: existing Brave/DDG/Bing HTML scrapers (often broken for RU).
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

log = logging.getLogger(__name__)


def serper_api_key() -> str:
    return (
        os.getenv("SERPER_API_KEY", "").strip()
        or os.getenv("SERPER_KEY", "").strip()
    )


async def serper_search(
    client: httpx.AsyncClient,
    query: str,
    *,
    num: int = 8,
    gl: str = "ru",
    hl: str = "ru",
) -> list[dict[str, str]]:
    """Return organic hits: {title, link, snippet}."""
    key = serper_api_key()
    if not key or not (query or "").strip():
        return []
    try:
        resp = await client.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY": key,
                "Content-Type": "application/json",
            },
            json={"q": query, "gl": gl, "hl": hl, "num": max(1, min(int(num), 20))},
            timeout=20.0,
        )
    except Exception as exc:
        log.info("serper failed: %s", exc)
        return []
    if resp.status_code >= 400:
        log.info("serper status %s: %s", resp.status_code, (resp.text or "")[:200])
        return []
    data = resp.json() if resp.content else {}
    out: list[dict[str, str]] = []
    for row in data.get("organic") or []:
        if not isinstance(row, dict):
            continue
        link = str(row.get("link") or "").strip()
        if not link.startswith("http"):
            continue
        out.append(
            {
                "title": str(row.get("title") or "").strip(),
                "link": link,
                "snippet": str(row.get("snippet") or "").strip(),
            }
        )
    return out


async def yandex_search_links(
    client: httpx.AsyncClient, query: str, *, num: int = 8
) -> list[str]:
    """Best-effort Yandex HTML search — works better for RU FIO than Bing from VPS."""
    import re
    from urllib.parse import quote_plus, unquote

    if not (query or "").strip():
        return []
    try:
        resp = await client.get(
            f"https://yandex.ru/search/?text={quote_plus(query)}&lr=213",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "ru-RU,ru;q=0.9",
            },
            timeout=18.0,
        )
    except Exception as exc:
        log.info("yandex search failed: %s", exc)
        return []
    if resp.status_code >= 400:
        return []
    html = resp.text or ""
    links: list[str] = []
    for raw in re.findall(r'href="(https?://[^"]+)"', html):
        url = raw.split("&amp;")[0]
        if "yandex." in url or "google." in url or "bing." in url:
            continue
        if "/search" in url and "vk." not in url:
            continue
        if url.startswith("http"):
            links.append(url.split("?")[0] if "vk." in url else url)
        if len(links) >= num * 3:
            break
    # Prefer vk links first
    links = sorted(links, key=lambda u: (0 if "vk.com" in u or "vk.ru" in u else 1, u))
    out: list[str] = []
    seen: set[str] = set()
    for u in links:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= num:
            break
    return out


async def web_search(
    client: httpx.AsyncClient,
    query: str,
    *,
    num: int = 8,
) -> list[dict[str, str]]:
    """Best available search: Serper API → Yandex → HTML scrapers."""
    hits = await serper_search(client, query, num=num)
    if hits:
        return hits
    yandex_links = await yandex_search_links(client, query, num=num)
    if yandex_links:
        return [{"title": "", "link": u, "snippet": ""} for u in yandex_links]
    # Fallback scrapers (often empty/poisoned for RU from this host)
    try:
        from app.contacts import _bing_links

        links = await _bing_links(client, query)
    except Exception:
        links = []
    return [{"title": "", "link": u, "snippet": ""} for u in (links or [])[:num]]


async def web_search_links(
    client: httpx.AsyncClient, query: str, *, num: int = 8
) -> list[str]:
    return [h["link"] for h in await web_search(client, query, num=num) if h.get("link")]
