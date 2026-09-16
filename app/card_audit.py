"""Final one-shot LLM audit+fix of an assembled hunt card.

One RouterAI JSON call (no web): validate object↔INN↔contacts and, when
possible, pick a better INN from already-fetched cheap candidates. No second
LLM call — swaps are hydrated via DaData/FNS only.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.cost_guard import llm_card_audit_enabled
from app.enrich import enrich_from_dadata, merge_fns_finance
from app.llm import RouterAI
from app.objects import object_company_relation

log = logging.getLogger(__name__)

SYSTEM = """Ты финальный контролёр одной карточки B2B-охоты по зданию в России.
Тебе дают: запрос, объект (здание), текущее юрлицо, контакты и список УЖЕ найденных
кандидатов ИНН (без интернета). Платный web НЕ используй.

Задача в ОДНОМ ответе — ПРОВЕРИТЬ и ПОПРАВИТЬ данные. Карточку НЕ удалять.
1) Сверь объект ↔ юрлицо ↔ контакты на достоверность.
2) Если текущий ИНН неверный, а в candidates есть лучше — укажи use_inn (только из candidates/current).
3) Если телефон/ВК/сайт/почта чужие или мусор — поставь clear_*=true (обнулить поле).
4) Не выдумывай ИНН вне списка.
5) Вердикт reject ЗАПРЕЩЁН как «выкинуть карточку». Если данные слабые —
   ставь warn и поправь что можно; карточку всегда оставляем менеджеру.

Правила:
- ТСЖ/ЖСК на другой улице для БЦ/ТЦ/склада — смени ИНН или warn + clear чужих контактов.
- Совпадение только города/индекса/района — не доказательство.
- Контакты самого объекта/ТЦ/БЦ допустимы для продажи подсветки здания, даже если
  они не доказывают собственника. Не очищай site/phone, когда источник явно объектный.
- Если сменил ИНН — verdict=accept или warn.

Ответ строго JSON без markdown:
{
  "verdict": "accept"|"warn",
  "confidence": 0-100,
  "object_ok": true|false,
  "company_ok": true|false,
  "contacts_ok": true|false,
  "use_inn": ""|"10 или 12 цифр из candidates/current",
  "clear_phone": true|false,
  "clear_vk": true|false,
  "clear_site": true|false,
  "clear_email": true|false,
  "reason": "1-2 предложения по-русски",
  "issues": ["краткий пункт"],
  "relation_status": "подтверждена"|"вероятная связь"|"предположительная связь"|"связь не подтверждена",
  "relation_confidence": 0-99
}
"""


def _clip(text: Any, limit: int = 240) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def _inn_digits(value: Any) -> str:
    inn = re.sub(r"\D", "", str(value or ""))
    return inn if len(inn) in (10, 12) else ""


def summarize_owner_candidates(cands: list[dict[str, Any]] | None, *, limit: int = 6) -> list[dict[str, Any]]:
    """Compact already-fetched owner candidates for the single LLM call."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for cand in cands or []:
        if not isinstance(cand, dict):
            continue
        inn = _inn_digits(cand.get("inn"))
        if not inn or inn in seen:
            continue
        seen.add(inn)
        party = cand.get("party") if isinstance(cand.get("party"), dict) else {}
        suggest = cand.get("suggest") if isinstance(cand.get("suggest"), dict) else {}
        enriched = party or (enrich_from_dadata(suggest) if suggest else {})
        out.append(
            {
                "inn": inn,
                "name": _clip(enriched.get("name") or cand.get("name") or ""),
                "address": _clip(enriched.get("address") or cand.get("address") or "", 280),
                "okved": _clip(enriched.get("okved") or cand.get("okved") or ""),
                "source": _clip(cand.get("source") or ""),
                "resolver_score": int(cand.get("resolver_score") or 0),
                "reasons": [
                    _clip(r, 120)
                    for r in (cand.get("resolver_reasons") or [])[:3]
                    if str(r or "").strip()
                ],
            }
        )
        if len(out) >= limit:
            break
    return out


def card_audit_payload(
    company: dict[str, Any],
    *,
    query: str = "",
    city: str = "",
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    obj = company.get("object") if isinstance(company.get("object"), dict) else {}
    rel = obj.get("relation") if isinstance(obj.get("relation"), dict) else {}
    presence = company.get("presence") if isinstance(company.get("presence"), dict) else {}
    phone = presence.get("phone") if isinstance(presence.get("phone"), dict) else {}
    vk = presence.get("vk_company") if isinstance(presence.get("vk_company"), dict) else {}
    vk_lpr = presence.get("vk_lpr") if isinstance(presence.get("vk_lpr"), dict) else {}
    site = presence.get("site") if isinstance(presence.get("site"), dict) else {}
    cand_rows = summarize_owner_candidates(
        candidates
        if candidates is not None
        else (company.get("owner_candidates") if isinstance(company.get("owner_candidates"), list) else [])
    )
    current_inn = _inn_digits(company.get("inn"))
    if current_inn and all(row["inn"] != current_inn for row in cand_rows):
        cand_rows.insert(
            0,
            {
                "inn": current_inn,
                "name": _clip(company.get("name") or ""),
                "address": _clip(company.get("address") or "", 280),
                "okved": _clip(company.get("okved") or ""),
                "source": "current",
                "resolver_score": int((rel or {}).get("confidence") or 0),
                "reasons": ["текущая карточка"],
            },
        )
    return {
        "query": _clip(query or company.get("search_phrase") or company.get("found_via") or ""),
        "city": _clip(city or company.get("requested_city") or ""),
        "object": {
            "title": _clip(obj.get("title") or ""),
            "address": _clip(obj.get("address") or company.get("object_address") or "", 320),
            "source": _clip(obj.get("source") or ""),
            "relation_status": _clip(rel.get("status") or ""),
            "relation_confidence": rel.get("confidence"),
            "relation_reason": _clip(rel.get("reason") or "", 400),
        },
        "company": {
            "inn": current_inn,
            "name": _clip(company.get("name") or ""),
            "okved": _clip(company.get("okved") or ""),
            "address": _clip(company.get("address") or "", 320),
            "management": _clip(
                company.get("management_label") or company.get("management") or ""
            ),
        },
        "contacts": {
            "phone": _clip(phone.get("value") or ""),
            "phone_status": _clip(phone.get("status") or ""),
            "phone_sources": [
                {
                    "value": _clip(item.get("value") or ""),
                    "source": _clip(item.get("source") or "", 160),
                }
                for item in (presence.get("phone_sources") or company.get("phone_sources") or [])[:4]
                if isinstance(item, dict)
            ],
            "vk_company": _clip(vk.get("value") or ""),
            "vk_lpr": _clip(vk_lpr.get("value") or ""),
            "site": _clip(site.get("value") or ""),
            "site_status": _clip(site.get("status") or ""),
            "site_hint": _clip(site.get("hint") or "", 220),
        },
        "candidates": cand_rows,
    }


def _normalize_verdict(
    raw: dict[str, Any] | None,
    *,
    allowed_inns: set[str],
    current_inn: str,
) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    verdict = str(data.get("verdict") or "").strip().lower()
    # Product rule: never discard a card — reject means «fix/warn and keep».
    if verdict == "reject":
        verdict = "warn"
    if verdict not in {"accept", "warn"}:
        verdict = "warn"
    try:
        confidence = int(data.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0
    confidence = min(max(confidence, 0), 100)
    try:
        rel_conf = int(data.get("relation_confidence") or 0)
    except (TypeError, ValueError):
        rel_conf = 0
    rel_conf = min(max(rel_conf, 0), 99)
    issues = [
        _clip(item, 160)
        for item in (data.get("issues") or [])
        if str(item or "").strip()
    ][:6]
    status = _clip(data.get("relation_status") or "")
    if not status:
        status = {
            "accept": "вероятная связь",
            "warn": "предположительная связь",
        }[verdict]
    use_inn = _inn_digits(data.get("use_inn"))
    if use_inn and use_inn not in allowed_inns:
        use_inn = ""
    if not use_inn:
        use_inn = current_inn
    return {
        "verdict": verdict,
        "confidence": confidence,
        "object_ok": bool(data.get("object_ok")) if "object_ok" in data else True,
        "company_ok": bool(data.get("company_ok")) if "company_ok" in data else verdict == "accept",
        "contacts_ok": bool(data.get("contacts_ok")) if "contacts_ok" in data else True,
        "use_inn": use_inn,
        "clear_phone": bool(data.get("clear_phone")),
        "clear_vk": bool(data.get("clear_vk")),
        "clear_site": bool(data.get("clear_site")),
        "clear_email": bool(data.get("clear_email")),
        "reason": _clip(data.get("reason") or "LLM-аудит без подробностей", 400),
        "issues": issues,
        "relation_status": status,
        "relation_confidence": rel_conf,
        "swapped": bool(use_inn and current_inn and use_inn != current_inn),
        "keep_card": True,
    }


def _clear_presence_field(presence: dict[str, Any], key: str) -> None:
    cur = presence.get(key)
    if isinstance(cur, dict):
        presence[key] = {**cur, "status": "нет", "value": ""}
    else:
        presence[key] = {"status": "нет", "value": ""}


def apply_contact_fixes(company: dict[str, Any], audit: dict[str, Any]) -> None:
    presence = company.get("presence") if isinstance(company.get("presence"), dict) else {}
    if audit.get("clear_phone"):
        _clear_presence_field(presence, "phone")
        company["phones"] = []
        presence["phone_sources"] = []
        company["phone_sources"] = []
    if audit.get("clear_vk"):
        _clear_presence_field(presence, "vk_company")
        _clear_presence_field(presence, "vk_group")
        _clear_presence_field(presence, "vk_lpr")
    if audit.get("clear_site"):
        _clear_presence_field(presence, "site")
        company["sites"] = []
    if audit.get("clear_email"):
        _clear_presence_field(presence, "email")
        company["emails"] = []
    company["presence"] = presence


def apply_card_audit(company: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    """Mutate stamp/relation/checks/contact clears. Never drops the card."""
    presence = company.get("presence") if isinstance(company.get("presence"), dict) else {}
    checks = list(presence.get("checks") or company.get("checks") or [])
    site_item = presence.get("site") if isinstance(presence.get("site"), dict) else {}
    site_status = str(site_item.get("status") or "").lower()
    site_hint = str(site_item.get("hint") or "").lower()
    phone_sources = presence.get("phone_sources") or company.get("phone_sources") or []
    has_object_phone = any(
        "сайт объекта" in str(item.get("source") or "").lower()
        for item in phone_sources
        if isinstance(item, dict)
    )
    has_object_site = "контакт объекта" in site_status or "названию здания" in site_hint
    if audit.get("clear_phone") and has_object_phone:
        audit["clear_phone"] = False
        checks.append("LLM-аудит: телефон сохранён как контакт объекта")
    if audit.get("clear_site") and has_object_site:
        audit["clear_site"] = False
        checks.append("LLM-аудит: сайт сохранён как контакт объекта")
    verdict = audit["verdict"]
    if verdict == "reject":
        verdict = "warn"
        audit["verdict"] = "warn"
    reason = audit["reason"]
    issues = audit.get("issues") or []
    if audit.get("swapped"):
        label = f"LLM-аудит: заменён ИНН → {audit.get('use_inn')}"
    elif verdict == "accept":
        label = "LLM-аудит: принято"
    else:
        label = "LLM-аудит: перепроверить"
    checks.append(f"{label} — {reason}")
    for issue in issues[:3]:
        checks.append(f"LLM-аудит: {issue}")
    apply_contact_fixes(company, audit)
    presence = company.get("presence") if isinstance(company.get("presence"), dict) else {}
    presence["checks"] = checks
    company["presence"] = presence
    company["checks"] = checks
    company["card_audit"] = {**audit, "keep_card": True, "verdict": verdict}

    obj = dict(company.get("object") or {}) if isinstance(company.get("object"), dict) else {}
    rel = dict(obj.get("relation") or {}) if isinstance(obj.get("relation"), dict) else {}
    if audit.get("relation_status"):
        rel["status"] = audit["relation_status"]
    if audit.get("relation_confidence") is not None:
        rel["confidence"] = int(audit["relation_confidence"])
    rel["llm_audit"] = verdict
    rel["llm_reason"] = reason
    if audit.get("swapped"):
        rel["llm_swapped_inn"] = audit.get("use_inn")
    obj["relation"] = rel
    company["object"] = obj

    # Never «стоп» from audit — keep card, mark for human recheck when needed.
    if verdict == "warn" or audit.get("swapped"):
        company["stamp"] = "осторожно"
        company["score"] = min(int(company.get("score") or 0), 55 if verdict == "warn" else 70)
        if audit.get("swapped"):
            company["stamp_hint"] = f"ИНН поправлен LLM-аудитом: {reason}"
        else:
            company["stamp_hint"] = f"Перепроверить связку объект↔ИНН: {reason}"
    return audit


async def swap_company_inn(
    company: dict[str, Any],
    new_inn: str,
    *,
    dadata: Any,
    fns: Any,
) -> bool:
    """Replace legal-entity fields via DaData/FNS only (no second LLM)."""
    inn = _inn_digits(new_inn)
    if not inn:
        return False
    try:
        raw = await dadata.find_by_inn(inn)
    except Exception as exc:
        log.info("card audit swap DaData failed %s: %s", inn, exc)
        return False
    if not raw:
        return False
    keep_object = company.get("object") if isinstance(company.get("object"), dict) else {}
    keep_photos = list(company.get("photos") or [])
    keep_object_address = company.get("object_address") or ""
    keep_search = company.get("search_phrase") or ""
    keep_city = company.get("requested_city") or ""
    keep_found_via = company.get("found_via") or ""
    keep_idea = company.get("idea") or ""
    keep_sphere = company.get("sphere") or ""
    keep_cands = company.get("owner_candidates") or []
    keep_checks = list((company.get("presence") or {}).get("checks") or company.get("checks") or [])

    flat = enrich_from_dadata(raw)
    try:
        flat = await merge_fns_finance(flat, fns)
    except Exception:
        pass
    flat["object"] = keep_object
    flat["photos"] = keep_photos
    flat["object_address"] = keep_object_address or flat.get("object_address") or ""
    flat["search_phrase"] = keep_search
    flat["requested_city"] = keep_city
    flat["found_via"] = f"{keep_found_via} · llm-swap".strip(" ·")
    flat["idea"] = keep_idea
    flat["sphere"] = keep_sphere
    flat["owner_candidates"] = keep_cands
    flat["kp"] = {}
    flat["kp_status"] = "отложено"
    # Registry-only presence after swap — contacts of the old INN must not stick.
    flat["presence"] = {
        "lpr": {
            "status": "найдено" if flat.get("management") else "нет",
            "value": flat.get("management_label") or flat.get("management") or "",
            "post": flat.get("management_post") or "",
            "source": "ЕГРЮЛ",
            "hint": "ЛПР после замены ИНН LLM-аудитом (без повторного LLM)",
        },
        "site": {"status": "нет", "value": ""},
        "phone": {"status": "нет", "value": ""},
        "email": {"status": "нет", "value": ""},
        "vk_company": {"status": "нет", "value": ""},
        "vk_group": {"status": "нет", "value": ""},
        "vk_lpr": {"status": "нет", "value": ""},
        "telegram": {"status": "нет", "value": ""},
        "whatsapp": {"status": "нет", "value": ""},
        "max": {"status": "нет", "value": ""},
        "checks": keep_checks
        + [f"LLM-аудит: юрлицо заменено на ИНН {inn} без второго LLM-вызова"],
        "phone_sources": [],
    }
    flat["phones"] = list(flat.get("phones") or [])
    flat["emails"] = list(flat.get("emails") or [])
    flat["sites"] = list(flat.get("sites") or [])
    if keep_object:
        flat["object"] = {
            **keep_object,
            "relation": object_company_relation(flat, keep_object),
        }
    company.clear()
    company.update(flat)
    return True


async def audit_assembled_card(
    llm: RouterAI | None,
    company: dict[str, Any],
    *,
    query: str = "",
    city: str = "",
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """One JSON audit call. Returns normalized audit with optional use_inn fix."""
    if not llm_card_audit_enabled():
        return None
    if llm is None or not getattr(llm, "available", False):
        return None
    payload = card_audit_payload(
        company, query=query, city=city, candidates=candidates
    )
    if not payload["object"].get("title") and not payload["company"].get("inn"):
        return None
    allowed = {row["inn"] for row in payload.get("candidates") or [] if row.get("inn")}
    current_inn = _inn_digits(payload.get("company", {}).get("inn"))
    if current_inn:
        allowed.add(current_inn)
    try:
        raw = await llm.chat_json(
            [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
            temperature=0.0,
            max_tokens=480,
            web=False,
        )
    except Exception as exc:
        log.info("card audit failed for %s: %s", company.get("inn"), exc)
        return None
    return _normalize_verdict(raw, allowed_inns=allowed, current_inn=current_inn)


async def run_final_card_audit(
    llm: RouterAI | None,
    company: dict[str, Any],
    *,
    query: str = "",
    city: str = "",
    dadata: Any = None,
    fns: Any = None,
    candidates: list[dict[str, Any]] | None = None,
    ensure_candidates: Any = None,
) -> dict[str, Any] | None:
    """Universal end-gate for every hunt card: one LLM call, optional INN swap.

    ``ensure_candidates`` may cheaply refresh owner candidates when the list is
    thin. Still no second LLM call — swap goes through DaData/FNS only.
    """
    cands = list(
        candidates
        if candidates is not None
        else (
            company.get("owner_candidates")
            if isinstance(company.get("owner_candidates"), list)
            else []
        )
    )
    if ensure_candidates is not None and len(summarize_owner_candidates(cands)) < 2:
        try:
            more = await ensure_candidates()
            if isinstance(more, list) and more:
                cands = more
                company["owner_candidates"] = more
        except Exception as exc:
            log.info("ensure_candidates failed: %s", exc)
    company["owner_candidates"] = cands
    audit = await audit_assembled_card(
        llm,
        company,
        query=query,
        city=city,
        candidates=cands,
    )
    if not audit:
        return None
    if audit.get("swapped") and audit.get("use_inn") and dadata is not None:
        swapped_ok = await swap_company_inn(
            company,
            str(audit.get("use_inn") or ""),
            dadata=dadata,
            fns=fns,
        )
        if not swapped_ok:
            audit["swapped"] = False
            audit["use_inn"] = _inn_digits(company.get("inn"))
            audit["verdict"] = "warn"
            audit["reason"] = (
                f"{audit.get('reason')}; замена ИНН не удалась — карточку оставили с пометкой"
            )[:400]
    apply_card_audit(company, audit)
    return audit
