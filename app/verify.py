from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.llm import RouterAI

log = logging.getLogger(__name__)

JUDGE_KEYS = (
    "site",
    "vk_company",
    "vk_lpr",
    "telegram",
    "whatsapp",
    "max",
    "web_lpr",
)

SYSTEM = """Ты агент-исследователь контактов B2B-компании в России.
Тебе дают карточку юрлица, телефоны из разных источников, кандидаты ссылок и ВЫЖИМКИ публичных страниц (excerpt).
Твоя работа как следователя:
1) Прочитай excerpt: упоминается ли ИНН, название, адрес, город, директор?
2) Сопоставь телефоны из phone_sources — один и тот же номер в 2+ местах = выше доверие.
3) Оставь только ссылки, которые относятся к ЭТОЙ компании / ЛПР.
4) Выбери лучший канал выхода для менеджера.

Правила:
- Сайт ≠ ВК ≠ Telegram ≠ WhatsApp ≠ Max — не дублируй URL.
- ВК компании: vk.com про организацию (в excerpt — название/ИНN/адрес).
- ВК ЛПР: только реальный личный профиль руководителя из management (ФИО на странице).
  Запрещено выдумывать id (id123456 и т.п.). Нет подтверждения по ФИО — keep=false, url="".
- site_trusted=true — сайт из List-Org/ЕГРЮЛ, бренд может ≠ юр. имя (Озон ↔ Интернет Решения).
- Каталоги zavod.ru, агрегаторы — reject.
- Если excerpt не подтверждает связь — reject (лучше «нет»).
- phone: выбери лучший подтверждённый номер из phone_sources или current; если нигде не бьётся — keep=false.

- Если is_smb=true (региональная компания, не федеральная сеть) — мягче по ВК ЛПР:
  достаточно совпадения ФИО руководителя в excerpt страницы vk.com, даже если URL без фамилии.
- lpr из ЕГРЮЛ не отменяй — это базовый ЛПР, даже если соцсетей нет.

Ответь строго JSON без markdown:
{
  "phone": {"keep": true|false, "value": "+7 ..."|"", "reason": "...", "confirmed_by": ["источник1", "источник2"]},
  "email": {"keep": true|false, "value": ""|string, "reason": "..."},
  "site": {"keep": true|false, "url": ""|string, "reason": "..."},
  "vk_company": {"keep": true|false, "url": ""|string, "reason": "..."},
  "vk_lpr": {"keep": true|false, "url": ""|string, "reason": "..."},
  "telegram": {"keep": true|false, "url": ""|string, "reason": "..."},
  "whatsapp": {"keep": true|false, "url": ""|string, "reason": "..."},
  "max": {"keep": true|false, "url": ""|string, "reason": "..."},
  "web_lpr": {"keep": true|false, "url": ""|string, "reason": "..."},
  "recommend": {"channel": "phone|email|telegram|whatsapp|max|vk_company|vk_lpr|site|нет", "reason": "...", "opening": "..."},
  "object_hint": "кратко: что за объект (магазин/склад/завод/офис) по excerpt, 1 предложение"
}
"""


def _url_ok_for_key(key: str, url: str) -> bool:
    low = url.lower()
    if key.startswith("vk"):
        if "vk.com" not in low and "vk.ru" not in low:
            return False
        if key == "vk_lpr":
            # Block classic LLM placeholders
            if re.search(r"/id(123456|111111|000000|999999|12345)\b", low):
                return False
            if "/club" in low or "/public" in low:
                return False
        return True
    if key == "telegram":
        return "t.me" in low or "telegram." in low
    if key == "whatsapp":
        return "wa.me" in low or "whatsapp.com" in low or "api.whatsapp" in low
    if key == "max":
        return "max.ru" in low or "max.me" in low
    if key == "site":
        return "vk.com" not in low and "t.me/" not in low and "wa.me" not in low
    return True


def _digits(phone: str) -> str:
    d = re.sub(r"\D", "", phone or "")
    if len(d) == 11 and d[0] in "78":
        return "7" + d[1:]
    if len(d) == 10:
        return "7" + d
    return d


async def investigate_presence(
    llm: RouterAI,
    *,
    company: str,
    inn: str,
    city: str,
    address: str,
    fio: str,
    presence: dict[str, Any],
    candidates: dict[str, list[str]] | None = None,
    snippets: list[dict[str, Any]] | None = None,
    phone_sources: list[dict[str, str]] | None = None,
    site_trusted: bool = False,
    is_smb: bool = False,
) -> dict[str, Any]:
    """Agent-3 investigator: reads page excerpts, verifies contacts, picks channel."""
    if not llm.available:
        return presence

    candidates = candidates or {}
    snippets = snippets or []
    phone_sources = phone_sources or []

    current_links = {
        key: (presence.get(key) or {}).get("value") or ""
        for key in JUDGE_KEYS
    }
    current_phone = (presence.get("phone") or {}).get("value") or ""
    current_email = (presence.get("email") or {}).get("value") or ""

    if (
        not any(current_links.values())
        and not current_phone
        and not current_email
        and not any(candidates.values())
        and not snippets
    ):
        return presence

    user = {
        "company": company,
        "inn": inn,
        "city": city,
        "address": address,
        "management": fio,
        "site_trusted": site_trusted,
        "is_smb": is_smb,
        "current": {
            **current_links,
            "phone": current_phone,
            "email": current_email,
        },
        "phone_sources": phone_sources[:10],
        "candidates": {k: (candidates.get(k) or [])[:6] for k in JUDGE_KEYS},
        "page_snippets": snippets[:8],
    }

    try:
        verdict = await llm.chat_json(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=1400,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("investigate_presence failed: %s", exc)
        checks = list(presence.get("checks") or [])
        checks.append(f"Агент 3 (исследователь): ошибка — {exc}")
        presence["checks"] = checks
        return presence

    checks = list(presence.get("checks") or [])
    checks.append("Агент 3 (исследователь): сверка по открытым страницам")

    # Phone
    phone_item = verdict.get("phone") if isinstance(verdict, dict) else None
    if isinstance(phone_item, dict):
        keep = bool(phone_item.get("keep"))
        val = str(phone_item.get("value") or "").strip()
        reason = str(phone_item.get("reason") or "").strip()
        confirmed = phone_item.get("confirmed_by") or []
        if keep and val:
            presence["phone"] = {"status": "найдено", "value": val}
            conf = ", ".join(str(x) for x in confirmed[:4]) if confirmed else ""
            checks.append(
                f"LLM · телефон: ок"
                + (f" ({conf})" if conf else "")
                + (f" — {reason[:80]}" if reason else "")
            )
        elif reason:
            checks.append(f"LLM · телефон: нет — {reason[:100]}")

    email_item = verdict.get("email") if isinstance(verdict, dict) else None
    if isinstance(email_item, dict):
        keep = bool(email_item.get("keep"))
        val = str(email_item.get("value") or "").strip()
        reason = str(email_item.get("reason") or "").strip()
        if keep and val and "@" in val:
            presence["email"] = {"status": "найдено", "value": val}
            if reason:
                checks.append(f"LLM · email: ок — {reason[:80]}")
        elif reason and not keep:
            presence["email"] = {"status": "нет", "value": ""}
            checks.append(f"LLM · email: нет — {reason[:80]}")

    for key in JUDGE_KEYS:
        item = verdict.get(key) if isinstance(verdict, dict) else None
        if not isinstance(item, dict):
            continue
        keep = bool(item.get("keep"))
        url = str(item.get("url") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if keep and url and not _url_ok_for_key(key, url):
            keep = False
        if key == "site" and site_trusted and current_links.get("site"):
            cur = current_links["site"]
            low = cur.lower()
            if "zavod.ru" not in low and "factory.ru" not in low:
                keep = True
                url = url or cur
        if keep and url:
            presence[key] = {"status": "найдено", "value": url}
            if reason:
                checks.append(f"LLM · {key}: ок — {reason[:90]}")
        else:
            was = (presence.get(key) or {}).get("value") or ""
            if key in presence and not (keep and url):
                if was and not keep:
                    presence[key] = {"status": "нет", "value": ""}
            if was or reason:
                checks.append(f"LLM · {key}: нет" + (f" — {reason[:90]}" if reason else ""))

    rec = verdict.get("recommend") if isinstance(verdict, dict) else None
    if isinstance(rec, dict):
        channel = str(rec.get("channel") or "").strip().lower()
        reason = str(rec.get("reason") or "").strip()
        opening = str(rec.get("opening") or "").strip()
        if channel and channel != "нет":
            presence["recommend"] = {
                "status": "найдено",
                "value": channel,
                "reason": reason,
                "opening": opening,
            }
            checks.append(f"LLM · выход: {channel}" + (f" — {reason[:70]}" if reason else ""))
        else:
            presence["recommend"] = {"status": "нет", "value": "", "reason": reason, "opening": ""}

    hint = str(verdict.get("object_hint") or "").strip() if isinstance(verdict, dict) else ""
    if hint:
        presence["object_hint"] = {"status": "найдено", "value": hint}

    presence["checks"] = checks
    presence["llm_verdict"] = verdict
    return presence


# Backward-compatible alias
verify_presence = investigate_presence
