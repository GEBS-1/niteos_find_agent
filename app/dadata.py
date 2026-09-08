from __future__ import annotations

from typing import Any

import httpx

SUGGEST_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party"
FIND_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"


class DaDataError(RuntimeError):
    pass


class DaData:
    def __init__(self, api_key: str, timeout: float = 20.0) -> None:
        if not api_key:
            raise DaDataError("Нет DADATA_API_KEY в .env")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def suggest(
        self,
        query: str,
        *,
        count: int = 20,
        okved: list[str] | None = None,
        locations: list[dict] | None = None,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {
            "query": query,
            "count": min(max(count, 1), 20),
            "status": ["ACTIVE"],
            "type": "LEGAL",
        }
        # Prefix codes like "25" make DaData return zero hits. Only full codes (47.11).
        full_okved = [c for c in (okved or []) if "." in c]
        if full_okved:
            body["okved"] = full_okved[:8]
        if locations:
            body["locations"] = locations
            body["locations_boost"] = locations
        response = await self._client.post(SUGGEST_URL, json=body)
        if response.status_code >= 400:
            raise DaDataError(f"DaData suggest {response.status_code}: {response.text[:300]}")
        return list(response.json().get("suggestions") or [])

    async def find_by_inn(self, inn: str) -> dict[str, Any] | None:
        response = await self._client.post(FIND_URL, json={"query": inn, "count": 1})
        if response.status_code >= 400:
            raise DaDataError(f"DaData findById {response.status_code}: {response.text[:300]}")
        items = response.json().get("suggestions") or []
        return items[0] if items else None


def _registration_date(state: dict[str, Any]) -> str:
    """DaData state.registration_date is ms since epoch → ДД.ММ.ГГГГ."""
    raw = state.get("registration_date")
    if raw in (None, "", 0):
        return ""
    try:
        from datetime import datetime, timezone

        ts = int(raw)
        if ts > 10_000_000_000:  # ms
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d.%m.%Y")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def flatten_party(suggestion: dict[str, Any]) -> dict[str, Any]:
    data = suggestion.get("data") or {}
    state = data.get("state") or {}
    management = data.get("management") or {}
    address = data.get("address") or {}
    name = data.get("name") or {}
    founded = _registration_date(state)
    return {
        "inn": data.get("inn") or "",
        "ogrn": data.get("ogrn") or "",
        "name": suggestion.get("value") or (name.get("short_with_opf") or name.get("full_with_opf") or ""),
        "okved": data.get("okved") or "",
        "address": address.get("unrestricted_value") or address.get("value") or "",
        "status": state.get("status") or "",
        "management": management.get("name") or "",
        "founded_at": founded,
        "payload": {
            "kpp": data.get("kpp"),
            "type": data.get("type"),
            "branch_type": data.get("branch_type"),
            "okved": data.get("okved"),
            "founded_at": founded,
            "registration_date": state.get("registration_date"),
        },
    }
