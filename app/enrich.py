from __future__ import annotations

from typing import Any

import httpx

from app.dadata import DaDataError, flatten_party


def _registration_date_from_state(state: dict[str, Any]) -> str:
    raw = state.get("registration_date") if isinstance(state, dict) else None
    if raw in (None, "", 0):
        return ""
    try:
        from datetime import datetime, timezone

        ts = int(raw)
        if ts > 10_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d.%m.%Y")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


BO_BASE = "https://bo.nalog.gov.ru"


def _money_thousands(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def format_money_rub(thousands: int | None) -> str:
    """BFO values are usually in thousand rubles."""
    if thousands is None:
        return "—"
    rub = thousands * 1000
    abs_rub = abs(rub)
    if abs_rub >= 1_000_000_000:
        text = f"{rub / 1_000_000_000:.2f}".rstrip("0").rstrip(".") + " млрд ₽"
    elif abs_rub >= 1_000_000:
        text = f"{rub / 1_000_000:.1f}".rstrip("0").rstrip(".") + " млн ₽"
    else:
        text = f"{rub:,}".replace(",", " ") + " ₽"
    return text


class FnsBfo:
    def __init__(self, timeout: float = 20.0) -> None:
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 NiteosHunt/1.0",
                "Accept": "application/json",
            },
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def finance_by_inn(self, inn: str) -> dict[str, Any]:
        inn = (inn or "").strip()
        if not inn:
            return {}
        search = await self._client.get(
            f"{BO_BASE}/advanced-search/organizations/search",
            params={"query": inn, "page": 0},
        )
        if search.status_code >= 400:
            raise DaDataError(f"FNS search {search.status_code}")
        content = (search.json() or {}).get("content") or []
        org = next((x for x in content if str(x.get("inn", "")).replace("<strong>", "").replace("</strong>", "") == inn), None)
        if not org and content:
            org = content[0]
        if not org:
            return {}
        oid = org.get("id")
        if not oid:
            return {}
        periods_resp = await self._client.get(f"{BO_BASE}/nbo/organizations/{oid}/bfo")
        if periods_resp.status_code >= 400:
            return {"assets": _money_thousands(org.get("actives")), "source": "fns_bfo"}
        periods = periods_resp.json() or []
        if not periods:
            return {}
        periods = sorted(periods, key=lambda p: int(p.get("period") or 0), reverse=True)
        chosen = next(
            (p for p in periods if p.get("gainSum") not in (None, 0)),
            None,
        )
        if chosen is None:
            chosen = next(
                (p for p in periods if p.get("gainSum") is not None),
                periods[0],
            )
        year = str(chosen.get("period") or "")
        revenue = _money_thousands(chosen.get("gainSum"))
        assets = _money_thousands(chosen.get("actives"))
        profit = None
        bid = chosen.get("id")
        if bid:
            details_resp = await self._client.get(f"{BO_BASE}/nbo/bfo/{bid}/details")
            if details_resp.status_code < 400:
                details = details_resp.json() or []
                item = details[0] if isinstance(details, list) and details else details
                if isinstance(item, dict):
                    fr = item.get("financialResult") or {}
                    cur_rev = _money_thousands(fr.get("current2110"))
                    prev_rev = _money_thousands(fr.get("previous2110"))
                    if cur_rev not in (None,):
                        revenue = cur_rev
                    elif prev_rev not in (None,):
                        revenue = prev_rev
                    cur_profit = _money_thousands(fr.get("current2400"))
                    prev_profit = _money_thousands(fr.get("previous2400"))
                    if cur_profit not in (None,):
                        profit = cur_profit
                    elif prev_profit not in (None,):
                        profit = prev_profit
                    # 2120 — расходы по обычным видам деятельности (тыс. ₽)
                    expense = _money_thousands(fr.get("current2120"))
                    if expense is None:
                        expense = _money_thousands(fr.get("previous2120"))
                else:
                    expense = None
            else:
                expense = None
        else:
            expense = None
        return {
            "year": year,
            "revenue": revenue,
            "profit": profit,
            "expense": expense,
            "assets": assets,
            "source": "fns_bfo",
        }


def enrich_from_dadata(suggestion: dict[str, Any]) -> dict[str, Any]:
    base = flatten_party(suggestion)
    data = suggestion.get("data") or {}
    management = data.get("management") or {}
    founders_raw = data.get("founders") or []
    managers_raw = data.get("managers") or []
    finance = data.get("finance") or {}
    phones = []
    for item in data.get("phones") or []:
        if isinstance(item, dict) and item.get("value"):
            phones.append(str(item["value"]))
        elif isinstance(item, str) and item.strip():
            phones.append(item.strip())
    emails = []
    for item in data.get("emails") or []:
        if isinstance(item, dict) and item.get("value"):
            emails.append(str(item["value"]))
        elif isinstance(item, str) and item.strip():
            emails.append(item.strip())
    sites = []
    for item in data.get("sites") or []:
        if isinstance(item, dict) and item.get("value"):
            sites.append(str(item["value"]))
        elif isinstance(item, str) and item.strip():
            sites.append(item.strip())

    founders: list[str] = []
    founders_detail: list[dict[str, Any]] = []
    for f in founders_raw:
        if not isinstance(f, dict):
            continue
        fio_obj = f.get("fio") if isinstance(f.get("fio"), dict) else {}
        fio = (fio_obj.get("source") if fio_obj else None) or ""
        name = str(f.get("name") or fio or "").strip()
        inn_f = str(f.get("inn") or "").strip()
        ftype = str(f.get("type") or "").strip().upper()
        share = f.get("share") or {}
        share_text = ""
        if isinstance(share, dict):
            if share.get("value") is not None:
                share_text = f"{share.get('value')}%"
            elif share.get("numerator") is not None and share.get("denominator"):
                share_text = f"{share.get('numerator')}/{share.get('denominator')}"
        if not name and not inn_f:
            continue
        role = "учредитель / выгодоприобретатель"
        if ftype == "LEGAL":
            role = "учредитель (юрлицо)"
        elif ftype == "PHYSICAL":
            role = "учредитель (физлицо)"
        line = name or "—"
        if inn_f:
            line = f"{line} · ИНН {inn_f}"
        if share_text:
            line = f"{line} · доля {share_text}"
        founders.append(line)
        founders_detail.append(
            {
                "name": name,
                "inn": inn_f,
                "share": share_text,
                "type": ftype or "",
                "role": role,
                "label": line,
            }
        )

    managers: list[str] = []
    for m in managers_raw:
        if not isinstance(m, dict):
            continue
        fio = ((m.get("fio") or {}).get("source") if isinstance(m.get("fio"), dict) else None) or ""
        name = m.get("name") or fio or ""
        post = m.get("post") or ""
        inn_m = str(m.get("inn") or "").strip()
        if name:
            bit = f"{name}" + (f" — {post}" if post else "")
            if inn_m:
                bit = f"{bit} · ИНН {inn_m}"
            managers.append(bit)

    post = (management.get("post") or "").strip()
    base["management_post"] = post
    if post and base.get("management"):
        base["management_label"] = f"{base['management']} — {post}"
    else:
        base["management_label"] = base.get("management") or ""

    base["founders"] = founders[:8]
    base["founders_detail"] = founders_detail[:8]
    base["managers"] = managers[:8]
    base["employee_count"] = data.get("employee_count")
    base["phones"] = phones[:5]
    base["emails"] = emails[:5]
    base["sites"] = sites[:5]
    if not base.get("founded_at"):
        base["founded_at"] = _registration_date_from_state(data.get("state") or {})
    base["revenue"] = _money_thousands(finance.get("revenue") if isinstance(finance, dict) else None)
    base["profit"] = None
    if isinstance(finance, dict):
        # DaData finance often has income/expense rather than profit.
        income = _money_thousands(finance.get("income"))
        expense = _money_thousands(finance.get("expense"))
        if base["revenue"] is None:
            base["revenue"] = _money_thousands(finance.get("revenue"))
        if income is not None and expense is not None:
            base["profit"] = income - expense
        base["finance_year"] = str(finance.get("year") or "") or None
    else:
        base["finance_year"] = None
    base["payload"] = {
        **(base.get("payload") or {}),
        "management_post": post,
        "founders": founders[:8],
        "founders_detail": founders_detail[:8],
        "managers": managers[:8],
        "employee_count": data.get("employee_count"),
        "phones": phones[:5],
        "emails": emails[:5],
        "sites": sites[:5],
        "finance": finance if isinstance(finance, dict) else {},
    }
    return base


async def merge_fns_finance(party: dict[str, Any], fns: FnsBfo) -> dict[str, Any]:
    try:
        fin = await fns.finance_by_inn(party.get("inn") or "")
    except Exception:
        return party
    if not fin:
        return party
    if party.get("revenue") is None and fin.get("revenue") is not None:
        party["revenue"] = fin.get("revenue")
    if party.get("profit") is None and fin.get("profit") is not None:
        party["profit"] = fin.get("profit")
    if party.get("expense") is None and fin.get("expense") is not None:
        party["expense"] = fin.get("expense")
    if not party.get("finance_year") and fin.get("year"):
        party["finance_year"] = fin.get("year")
    party["assets"] = fin.get("assets")
    party["finance_source"] = fin.get("source") or "fns_bfo"
    payload = dict(party.get("payload") or {})
    payload["fns_finance"] = fin
    party["payload"] = payload
    return party
