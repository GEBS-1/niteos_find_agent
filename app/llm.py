from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

log = logging.getLogger(__name__)


class RouterAI:
    """OpenAI-compatible client for https://routerai.ru (same shape as Concept Lite)."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://routerai.ru/api/v1",
        model: str = "openai/gpt-4o-mini",
        timeout: float = 45.0,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "https://routerai.ru/api/v1").rstrip("/")
        self.model = model or "openai/gpt-4o-mini"
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 700,
        model: str | None = None,
        web: bool = False,
        web_max_results: int = 8,
        web_engine: str = "exa",
        search_prompt: str | None = None,
    ) -> str:
        result = await self.chat_raw(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            web=web,
            web_max_results=web_max_results,
            web_engine=web_engine,
            search_prompt=search_prompt,
        )
        return str(result.get("content") or "").strip()

    async def chat_raw(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 700,
        model: str | None = None,
        web: bool = False,
        web_max_results: int = 8,
        web_engine: str = "exa",
        search_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Return content + optional url citations from RouterAI web plugin."""
        if not self.available:
            raise RuntimeError("RouterAI: нет ключа")
        use_model = model or self.model
        body: dict[str, Any] = {
            "model": use_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if web:
            # Built-in RouterAI web search — no Serper needed.
            # Docs: plugins id=web, or model suffix :online
            if ":online" not in use_model:
                body["model"] = use_model  # keep base model; plugins below
            prompt = (search_prompt or "").strip() or (
                "Ищи релевантные страницы по запросу пользователя: "
                "официальные сайты, карточки компаний, профили и группы ВКонтакте. "
                "Не подменяй сущность на похожую."
            )
            plugin: dict[str, Any] = {
                "id": "web",
                "max_results": max(1, min(int(web_max_results), 15)),
                "search_prompt": prompt,
            }
            if web_engine:
                plugin["engine"] = web_engine
            body["plugins"] = [plugin]
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = await self._client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=90.0 if web else None,
                )
                if resp.status_code in {401, 403}:
                    # Bad/expired key — no point retrying 3 times per building.
                    raise RuntimeError(
                        f"RouterAI {resp.status_code}: ключ отклонён"
                    )
                if resp.status_code >= 400:
                    raise RuntimeError(f"RouterAI {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                message = ((data.get("choices") or [{}])[0].get("message") or {})
                text = message.get("content")
                if not text:
                    raise RuntimeError("RouterAI: пустой ответ")
                citations = _extract_citations(message, data)
                return {
                    "content": str(text).strip(),
                    "citations": citations,
                    "raw": data,
                }
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                msg = str(exc)
                if "401" in msg or "403" in msg or "ключ отклонён" in msg:
                    break
                log.warning("routerai attempt %s failed: %s", attempt + 1, exc)
        raise RuntimeError(f"RouterAI недоступен: {last_err}")

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 700,
        web: bool = False,
        web_max_results: int = 8,
        web_engine: str = "exa",
        search_prompt: str | None = None,
    ) -> dict[str, Any]:
        raw = await self.chat_raw(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            web=web,
            web_max_results=web_max_results,
            web_engine=web_engine,
            search_prompt=search_prompt,
        )
        data = _extract_json(str(raw.get("content") or ""))
        if isinstance(data, dict):
            data["_citations"] = raw.get("citations") or []
            return data
        return {"_citations": raw.get("citations") or []}


def _extract_citations(message: dict[str, Any], data: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(url: str, title: str = "", snippet: str = "") -> None:
        url = (url or "").strip()
        if not url.startswith("http") or url in seen:
            return
        seen.add(url)
        out.append(
            {
                "link": url.split("?")[0].rstrip("/"),
                "title": (title or "")[:160],
                "snippet": (snippet or "")[:280],
            }
        )

    anns = message.get("annotations") or []
    if isinstance(anns, list):
        for ann in anns:
            if not isinstance(ann, dict):
                continue
            cite = ann.get("url_citation") if ann.get("type") == "url_citation" else ann
            if not isinstance(cite, dict):
                continue
            _add(
                str(cite.get("url") or ""),
                str(cite.get("title") or ""),
                str(cite.get("content") or cite.get("snippet") or ""),
            )

    # Some providers nest citations elsewhere
    for key in ("citations", "sources"):
        rows = data.get(key) or message.get(key) or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                _add(
                    str(row.get("url") or row.get("link") or ""),
                    str(row.get("title") or ""),
                    str(row.get("content") or row.get("snippet") or ""),
                )
            elif isinstance(row, str):
                _add(row)

    # Fallback: URLs inside assistant text
    content = str(message.get("content") or "")
    for url in re.findall(r"https?://[^\s\"'<>\]]+", content):
        _add(url.rstrip(").,;"))

    return out


def _extract_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}
