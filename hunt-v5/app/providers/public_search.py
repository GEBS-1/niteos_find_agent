from __future__ import annotations
import html as html_lib
import re
import httpx
from dataclasses import dataclass
from app.config import settings
from app.providers.free_web import HEADERS, web_links

@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str
    source: str

class NormalizedPublicSearchProvider:
    """Adapter contract for Yandex Search API / another search gateway.

    This prototype intentionally keeps search-provider auth/response parsing behind one
    adapter. Configure PUBLIC_SEARCH_API_URL to a gateway that returns:
      {"items":[{"title":"...","url":"...","snippet":"..."}]}

    The contact resolver may extract only contacts visibly present in returned public
    documents/pages and must keep the source URL.
    """
    async def search(self, query: str, limit: int = 10) -> list[SearchHit]:
        async with httpx.AsyncClient(timeout=18, headers=HEADERS, follow_redirects=True) as client:
            if not settings.public_search_api_url:
                return await self._free_search(client, query, limit)
            headers = {}
            if settings.public_search_api_key:
                headers["Authorization"] = f"Bearer {settings.public_search_api_key}"
            r = await client.get(settings.public_search_api_url, params={"q": query, "limit": limit}, headers=headers)
            r.raise_for_status()
            data = r.json()
        return [SearchHit(
            title=str(x.get("title") or ""), url=str(x.get("url") or ""),
            snippet=str(x.get("snippet") or ""), source=str(x.get("source") or "public_search")
        ) for x in (data.get("items") or []) if x.get("url")]

    async def _free_search(self, client: httpx.AsyncClient, query: str, limit: int) -> list[SearchHit]:
        links = await web_links(client, query, limit=min(limit, 6))
        out: list[SearchHit] = []
        for url in links[: min(limit, 6)]:
            low = url.lower()
            if any(x in low for x in ("yandex.ru/maps", "2gis.ru", "google.com/maps", "youtube.")):
                continue
            title = ""
            snippet = ""
            try:
                response = await client.get(url, timeout=8.0)
                if response.status_code >= 400:
                    continue
                raw = response.text[:120_000]
                m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
                if m:
                    title = re.sub(r"\s+", " ", html_lib.unescape(m.group(1))).strip()
                text = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.I)
                text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
                text = re.sub(r"<[^>]+>", " ", text)
                snippet = re.sub(r"\s+", " ", html_lib.unescape(text)).strip()[:1600]
            except Exception:
                snippet = ""
            out.append(SearchHit(title=title or url, url=url, snippet=snippet, source="free_web"))
        return out
