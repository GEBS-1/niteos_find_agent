"""One-shot LLM hunt + free post-verify before the card is shown.

Flow:
1) One RouterAI web call -> draft JSON cards (with today's date in prompt)
2) Deterministic harden (no second LLM):
   - drop unverified LLM phones/emails/VK (no invention, no random)
   - DaData EGRUL by INN or by name
   - scrape official site: /contact/ phones+email, /about/management/ leadership
   - VK only if matches this company + city
   - exterior facade photos for architectural lighting
   - finance: prefer FNS latest year (2025+), else recent LLM only
"""
from __future__ import annotations

import hashlib
import html as htmllib
import json
import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus, urljoin

import httpx

from app.contacts import (
    _bing_links,
    _checko_party_facts,
    _ddg_links,
    _harvest_site,
    _looks_like_person_fio,
)
from app.enrich import enrich_from_dadata, format_money_rub, merge_fns_finance
from app.llm import RouterAI
from app.objects import collect_object_photos

log = logging.getLogger(__name__)


def _system_prompt(*, today: str, finance_year_hint: str) -> str:
    return f"""Ты работаешь как ChatGPT с доступом в интернет: по ОДНОМУ запросу пользователя
собери готовую карточку объекта для продажи архитектурной подсветки фасада.

Сейчас: {today}. Нужны АКТУАЛЬНЫЕ данные на эту дату (не архив прошлых лет).

Сделай веб-поиск и верни JSON. Без заглушек и без выдумок.
Доведи до конца главную цепочку: конкретное здание -> фото фасада -> кадастр/реестры -> собственник/эксплуатант -> физлица -> личные публичные контакты человека.

Обязательный чеклист:
1) Сначала найди КОНКРЕТНОЕ физическое здание в указанном городе/регионе, а не головное ПАО/холдинг без здания.
2) Проверь здание через карты/кадастровые/реестровые следы: адрес, точка, возможный кадастровый номер, собственник, эксплуатант, УК, арендатор. Не называй арендатора собственником без источника.
3) Если собственник юрлицо — раскрой ЕГРЮЛ/Checko/List-Org/ЗаЧестныйБизнес: ИНН, ОГРН, руководитель, физлица-учредители/бенефициары.
4) Цель контакта — ЧЕЛОВЕК: собственник-физлицо, бенефициар, руководитель собственника/эксплуатанта, главный инженер, главный энергетик, эксплуатация/facility/техдиректор. Общий телефон компании не считается личным контактом.
5) Для people[] ищи личные публичные каналы человека:
   - телефон/email только если опубликованы рядом с ФИО или в документе/профиле этого человека;
   - Telegram / WhatsApp / VK только если ссылка относится к этому человеку;
   - если есть только ФИО без контакта — оставь phone/email/vk/telegram/whatsapp пустыми.
6) Официальный сайт объекта/оператора в указанном городе можно вернуть отдельно как справку, но не подставляй его как контакт владельца.
7) ВК-ГРУППА объекта/оператора (вторичный источник, не личный контакт):
   - поиск ВКонтакте / в вебе: «{{название}} {{город}}», «{{название}} ВК», site:vk.com;
   - верни прямую ссылку на ГРУППУ/сообщество: https://vk.com/slug или https://vk.com/club123456
     (не /wall, не /board, не обсуждение, не личный профиль);
   - группа должна быть про ЭТУ компанию в ЭТОМ городе. Нет уверенности → пусто.
8) Финансы — выручка/прибыль за ПОСЛЕДНИЙ год (цель {finance_year_hint}, минимум ≥{finance_year_hint}):
   - сначала ЗаЧестныйБизнес (zachestnyibiznes.ru) по ИНН;
   - если ZCB недоступен/нет года — открытые публикации: cbonds, tadviser, e-disclosure, РБК/Интерфакс с цифрой РСБУ;
   - в sources.finance укажи URL источника с цифрой;
   - не выдумывай и не путай млн/млрд.
9) Фото (1–3 https URL) — НАРУЖНЫЙ ФАСАД здания с ракурса для архитектурной подсветки:
   - видно весь/большую часть фасада с улицы (3/4 или фронт), как для проекта освещения;
   - Яндекс.Карты org / панорама / сайт «о компании» / фото завода снаружи;
   - НЕ интерьер, НЕ станок/продукция, НЕ логотип, НЕ план, НЕ сток.
10) Адрес здания для выезда.

Запрещено: выдумывать ИНН/телефоны/почту/ВК/ФИО/финансы; выдавать общий телефон компании за личный телефон человека; ВК тёзки из другого города; коммерческого директора без источника; рандом/заглушки; стоковые фото.

Нет факта → пустая строка / null / []. Укажи sources (URL).

Ответ строго JSON без markdown:
{{
  "cards": [
    {{
      "object_title": "",
      "object_address": "",
      "company_name": "",
      "inn": "",
      "ogrn": "",
      "okved": "",
      "legal_address": "",
      "management": "",
      "management_post": "",
      "phone": "",
      "email": "",
      "site": "",
      "vk": "",
      "telegram": "",
      "revenue": null,
      "profit": null,
      "expense": null,
      "finance_year": "",
      "founders": [{{"name": "", "share": "", "type": "PHYSICAL|LEGAL"}}],
      "beneficiaries": [{{"name": "", "share": ""}}],
      "people": [
        {{
          "name": "ФИО",
          "role": "владелец/учредитель/главный инженер/техдиректор/эксплуатация",
          "phone": "",
          "email": "",
          "vk": "",
          "telegram": "",
          "whatsapp": "",
          "source": "URL где ФИО и контакт связаны",
          "why": "почему именно этот человек нужен для продажи"
        }}
      ],
      "photos": [],
      "maps_yandex": "",
      "confidence": 0,
      "notes": "кратко что нашёл",
      "sources": {{
        "inn": "",
        "phone": "",
        "email": "",
        "site": "",
        "vk": "",
        "management": "",
        "finance": "",
        "founders": "",
        "people": "",
        "photos": ""
      }}
    }}
  ]
}}
"""


SYSTEM = _system_prompt(today="сегодня", finance_year_hint="2025")


_FAKE_PHONE_RE = re.compile(
    r"(?:222[\-\s]?22[\-\s]?22|000[\-\s]?00[\-\s]?00|123[\-\s]?45[\-\s]?67|"
    r"111[\-\s]?11[\-\s]?11|999[\-\s]?99[\-\s]?99)",
    re.I,
)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+7|8)[\s\-\(]*\d{3}[\s\-\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}"
)
_VK_RE = re.compile(
    r"https?://(?:m\.)?vk\.(?:com|ru)/(?!share|away|login|images)[a-zA-Z0-9._/\-]+",
    re.I,
)


def _clip(text: Any, limit: int = 240) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def _inn_digits(value: Any) -> str:
    inn = re.sub(r"\D", "", str(value or ""))
    return inn if len(inn) in (10, 12) else ""


def _looks_fake_inn(inn: str) -> bool:
    inn = _inn_digits(inn)
    if not inn:
        return True
    if inn.startswith("OBJ-"):
        return True
    if len(set(inn)) <= 3:
        return True
    if inn.count("0") >= 5:
        return True
    if re.fullmatch(r"(\d)\1+", inn):
        return True
    if inn.endswith("0000") or inn.endswith("00000"):
        return True
    return False


def _looks_fake_phone(phone: str) -> bool:
    if not phone:
        return True
    if _FAKE_PHONE_RE.search(phone):
        return True
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 11:
        return True
    if len(set(digits[-7:])) <= 2:
        return True
    return False


def _looks_guessed_email(email: str, site: str) -> bool:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return True
    host = email.split("@", 1)[-1]
    if any(x in host for x in ("example.", "test.", "mail.ru", "gmail.", "yandex.")):
        # corporate mail.ru can be real — only block obvious generics without company
        if host in {"mail.ru", "gmail.com", "yandex.ru", "ya.ru"}:
            return True
    site_host = re.sub(r"^www\.", "", re.sub(r"^https?://", "", (site or "").lower())).split("/")[0]
    if site_host and host == site_host and email.startswith(("info@", "mail@", "office@")):
        # likely guessed from domain — keep only if later confirmed on site
        return True
    return False


def _money(value: Any) -> int | None:
    """Parse money to rubles (int)."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    raw = str(value).strip().lower().replace(" ", "").replace("\xa0", "")
    raw = raw.replace("руб.", "").replace("руб", "").replace("₽", "")
    mult = 1
    if "млрд" in raw:
        mult = 1_000_000_000
        raw = raw.replace("млрд", "")
    elif "млн" in raw:
        mult = 1_000_000
        raw = raw.replace("млн", "")
    elif "тыс" in raw:
        mult = 1_000
        raw = raw.replace("тыс", "")
    raw = raw.replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", raw)
    if not m:
        return None
    try:
        return int(float(m.group(0)) * mult)
    except ValueError:
        return None


def _money_thousands(value: Any) -> int | None:
    """LLM/human amounts → thousands of rubles (same unit as FNS/DaData)."""
    rub = _money(value)
    if rub is None:
        return None
    # Heuristic: plain ints from LLM without unit are often already thousands
    # when huge (>= 1e9 as "тыс" would be insane). Prefer rubles→тыс.
    if isinstance(value, (int, float)) and abs(int(value)) >= 1_000_000_000:
        # treat as rubles
        return int(value) // 1000
    if isinstance(value, str) and any(x in value.lower() for x in ("млрд", "млн", "тыс", "руб", "₽")):
        return rub // 1000
    if isinstance(value, (int, float)):
        # bare number: assume already thousands if < 1e11, else rubles
        n = int(value)
        if abs(n) >= 1_000_000_000_000:  # >= 1e12 → rubles
            return n // 1000
        return n
    return rub // 1000


def _presence_item(value: str, *, ok_status: str = "найдено", source: str = "") -> dict[str, str]:
    value = _clip(value, 300)
    if not value:
        return {"status": "нет", "value": "", "source": source}
    item = {"status": ok_status, "value": value}
    if source:
        item["source"] = source
    return item


_LPR_ROLE_RE = re.compile(
    r"ген(?:еральн\w*)?\s*директор|директор|руководител|собственник|бенефициар|"
    r"учредител|владелец|председатель|управляющ",
    re.I,
)
_FAST_ROLE_RE = re.compile(
    r"коммерческ|закупк|снабжен|сбыт|продаж|ахо|главн\w*\s*инженер|"
    r"секретар|приёмн|приемн|офис.?менеджер|маркетинг",
    re.I,
)


def _person_rank(role: str) -> int:
    role = role or ""
    if re.search(r"ген(?:еральн\w*)?\s*директор", role, re.I):
        return 0
    if re.search(r"\bдиректор\b|руководител", role, re.I):
        return 1
    if re.search(r"собственник|бенефициар|учредител|владелец", role, re.I):
        return 2
    if _FAST_ROLE_RE.search(role):
        return 3
    return 5


def _normalize_founder_rows(raw: Any) -> tuple[list[str], list[dict[str, Any]]]:
    founders: list[str] = []
    detail: list[dict[str, Any]] = []
    rows = raw if isinstance(raw, list) else []
    for item in rows[:8]:
        if isinstance(item, str):
            name = _clip(item, 160)
            if not name:
                continue
            founders.append(name)
            detail.append(
                {
                    "name": name,
                    "inn": "",
                    "share": "",
                    "type": "",
                    "role": "учредитель / выгодоприобретатель",
                    "label": name,
                }
            )
            continue
        if not isinstance(item, dict):
            continue
        name = _clip(item.get("name") or item.get("fio") or "", 160)
        share = _clip(item.get("share") or "", 32)
        ftype = _clip(item.get("type") or "", 16).upper()
        inn_f = _inn_digits(item.get("inn"))
        if not name:
            continue
        role = "учредитель / выгодоприобретатель"
        if ftype == "LEGAL":
            role = "учредитель (юрлицо)"
        elif ftype == "PHYSICAL":
            role = "учредитель (физлицо)"
        line = name
        if inn_f:
            line = f"{line} · ИНН {inn_f}"
        if share:
            line = f"{line} · доля {share}"
        founders.append(line)
        detail.append(
            {
                "name": name,
                "inn": inn_f,
                "share": share,
                "type": ftype,
                "role": role,
                "label": line,
            }
        )
    return founders, detail


def _normalize_people(raw: Any, *, default_source: str = "LLM oneshot") -> list[dict[str, str]]:
    people: list[dict[str, str]] = []
    rows = raw if isinstance(raw, list) else []
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = _clip(item.get("name") or item.get("fio") or "", 120)
        if not name or not _looks_like_person_fio(name):
            continue
        role = _clip(item.get("role") or item.get("post") or "", 80)
        phone = _clip(item.get("phone") or "", 64)
        if phone and _looks_fake_phone(phone):
            phone = ""
        email = _clip(item.get("email") or "", 120)
        if email and ("@" not in email or email.lower().endswith("@example.com")):
            email = ""
        vk = _clip(item.get("vk") or "", 200)
        if vk and "vk." not in vk.lower():
            vk = ""
        telegram = _clip(item.get("telegram") or item.get("tg") or "", 200)
        if telegram and not any(x in telegram.lower() for x in ("t.me/", "telegram.me/")):
            telegram = ""
        whatsapp = _clip(item.get("whatsapp") or item.get("wa") or "", 200)
        if whatsapp and not any(x in whatsapp.lower() for x in ("wa.me/", "whatsapp.com")):
            whatsapp = ""
        source = _clip(item.get("source") or default_source, 160)
        why = _clip(item.get("why") or "", 160)
        if not (phone or email or vk or telegram or whatsapp or _LPR_ROLE_RE.search(role) or _FAST_ROLE_RE.search(role)):
            # keep named LPR even without contact — still useful for outreach search
            if not role:
                continue
        people.append(
            {
                "name": name,
                "role": role or "контакт",
                "phone": phone,
                "email": email,
                "vk": vk,
                "telegram": telegram,
                "whatsapp": whatsapp,
                "source": source,
                "why": why,
            }
        )
    people.sort(key=lambda p: (_person_rank(p.get("role") or ""), 0 if p.get("phone") else 1))
    # de-dupe by name
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for p in people:
        key = p["name"].lower().replace("ё", "е")
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
        if len(out) >= 5:
            break
    return out


def _pseudo_inn(seed: str) -> str:
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"OBJ-{digest}"


def _add_check(card: dict[str, Any], text: str) -> None:
    presence = card.get("presence") if isinstance(card.get("presence"), dict) else {}
    checks = list(presence.get("checks") or card.get("checks") or [])
    if text and text not in checks:
        checks.append(text)
    presence["checks"] = checks
    card["presence"] = presence
    card["checks"] = checks


def _set_presence(card: dict[str, Any], key: str, value: str, *, source: str) -> None:
    presence = card.get("presence") if isinstance(card.get("presence"), dict) else {}
    presence[key] = _presence_item(value, source=source)
    card["presence"] = presence
    if key == "phone":
        card["phones"] = [value] if value else []
        card["phone_sources"] = [{"value": value, "source": source}] if value else []
        presence["phone_sources"] = card["phone_sources"]
    if key == "email":
        card["emails"] = [value] if value else []
    if key == "site":
        card["sites"] = [value] if value else []
    if key in {"vk_company", "vk_group"} and value:
        presence["vk_company"] = _presence_item(value, source=source)
        presence["vk_group"] = _presence_item(value, source=source)


def map_oneshot_card(
    raw: dict[str, Any],
    *,
    query: str,
    city: str,
    sphere: str = "",
    idea: str = "",
) -> dict[str, Any]:
    """Convert one LLM JSON card into the hunt company payload."""
    sources = raw.get("sources") if isinstance(raw.get("sources"), dict) else {}
    obj_title = _clip(raw.get("object_title") or raw.get("title") or "", 160)
    obj_addr = _clip(raw.get("object_address") or raw.get("address") or "", 320)
    company_name = _clip(raw.get("company_name") or raw.get("name") or obj_title, 200)
    inn_raw = _inn_digits(raw.get("inn"))
    inn = "" if _looks_fake_inn(inn_raw) else inn_raw
    if not inn:
        inn = _pseudo_inn(f"{obj_title}|{obj_addr}|{company_name}|{city}")

    phone = _clip(raw.get("phone") or "", 64)
    if _looks_fake_phone(phone):
        phone = ""
    email = _clip(raw.get("email") or "", 120)
    site = _clip(raw.get("site") or "", 200)
    if _looks_guessed_email(email, site):
        email = ""
    vk = _clip(raw.get("vk") or "", 200)
    if any(bad in vk.lower() for bad in ("/wall", "/board", "/topic", "/write")):
        vk = ""
    telegram = _clip(raw.get("telegram") or "", 200)
    management = _clip(raw.get("management") or "", 160)
    post = _clip(raw.get("management_post") or "", 80)
    legal = _clip(raw.get("legal_address") or obj_addr, 320)
    maps = _clip(raw.get("maps_yandex") or "", 400)
    if not maps and (obj_title or obj_addr):
        pin = f"{obj_title} {obj_addr} {city}".strip()
        maps = f"https://yandex.ru/maps/?text={quote_plus(pin)}"
    photos = [
        _clip(u, 400)
        for u in (raw.get("photos") or [])
        if isinstance(u, str) and u.startswith("http") and "placeholder" not in u.lower()
    ][:6]

    def src(key: str, default: str = "LLM oneshot") -> str:
        return _clip(sources.get(key) or default, 120)

    founders, founders_detail = _normalize_founder_rows(raw.get("founders"))
    _, bene_detail = _normalize_founder_rows(raw.get("beneficiaries"))
    for row in bene_detail:
        row["role"] = "бенефициар / выгодоприобретатель"
        label = row.get("name") or ""
        if row.get("share"):
            label = f"{label} · доля {row['share']}"
        row["label"] = label
        if label and label not in founders:
            founders.append(label)
            founders_detail.append(row)

    people = _normalize_people(
        raw.get("people") or raw.get("lpr_contacts") or [],
        default_source=src("people"),
    )
    if people:
        top = people[0]
        if not management or not _looks_like_person_fio(management):
            management = top["name"]
            if not post:
                post = top.get("role") or post

    managers = [
        (
            f"{p['name']}"
            + (f" — {p['role']}" if p.get("role") else "")
            + (f" · {p['phone']}" if p.get("phone") else "")
            + (f" · {p['email']}" if p.get("email") else "")
        )
        for p in people
    ]

    # LLM finance kept only as draft for harden (ЗаЧестныйБизнес) — not shown until verified
    revenue = None
    profit = None
    expense = None
    llm_fin_draft = {
        "revenue": _money_thousands(raw.get("revenue")),
        "profit": _money_thousands(raw.get("profit")),
        "expense": _money_thousands(raw.get("expense")),
        "finance_year": _clip(raw.get("finance_year") or "", 8),
        "finance_source": _clip(sources.get("finance") or "", 200),
    }

    try:
        confidence = int(raw.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0
    confidence = min(max(confidence, 0), 99)
    notes = _clip(raw.get("notes") or "карточка из одного LLM-запроса", 400)
    stamp = "в работу" if confidence >= 70 and not str(inn).startswith("OBJ-") else "осторожно"
    score = max(40, confidence) if stamp == "в работу" else min(55, max(35, confidence))

    lpr_phone = next((p["phone"] for p in people if p.get("phone")), "")
    lpr_email = next((p["email"] for p in people if p.get("email")), "")
    lpr_vk = next((p["vk"] for p in people if p.get("vk")), "")
    lpr_telegram = next((p["telegram"] for p in people if p.get("telegram")), "")
    lpr_whatsapp = next((p["whatsapp"] for p in people if p.get("whatsapp")), "")
    display_phone = lpr_phone or phone
    phone_sources: list[dict[str, str]] = []
    if lpr_phone:
        phone_sources.append(
            {
                "value": lpr_phone,
                "source": next(
                    (p.get("source") or src("people") for p in people if p.get("phone") == lpr_phone),
                    src("people"),
                ),
            }
        )
    if phone and phone != lpr_phone:
        phone_sources.append({"value": phone, "source": src("phone")})

    lpr_label = f"{management} — {post}".strip(" —") if management else ""
    presence = {
        "lpr": {
            "status": "найдено" if management else "нет",
            "value": lpr_label,
            "post": post,
            "phone": lpr_phone,
            "email": lpr_email,
            "source": src("management") if management else "",
            "hint": "Проверьте ЛПР перед звонком",
        },
        "site": _presence_item(site, source=src("site")),
        "phone": _presence_item(
            display_phone,
            source=(phone_sources[0]["source"] if phone_sources else src("phone")),
        ),
        "email": _presence_item(
            email or lpr_email,
            source=src("email") if email else src("people"),
        ),
        "vk_company": _presence_item(vk, source=src("vk")),
        "vk_group": _presence_item(vk, source=src("vk")),
        "vk_lpr": _presence_item(lpr_vk, source=src("people")) if lpr_vk else {"status": "нет", "value": ""},
        "telegram": _presence_item(lpr_telegram or telegram),
        "whatsapp": _presence_item(lpr_whatsapp),
        "max": {"status": "нет", "value": ""},
        "maps_yandex": {"status": "открыть" if maps else "нет", "value": maps},
        "people": {
            "status": "найдено" if people else "нет",
            "value": people,
            "source": src("people"),
        },
        "checks": [
            f"LLM oneshot draft: {notes}",
            f"источник ИНН: {src('inn', 'не указан / требует сверки')}",
        ],
        "phone_sources": phone_sources,
    }
    if revenue is not None or profit is not None or expense is not None:
        presence["checks"].append(
            f"Финансы LLM: {src('finance', 'Checko/ЗаЧестныйБизнес/открытые источники')}"
        )
    if founders:
        presence["checks"].append(
            f"Учредители/бенефициары: {len(founders)} ({src('founders', 'реестры')})"
        )
    if people:
        with_contact = sum(
            1
            for p in people
            if p.get("phone") or p.get("email") or p.get("vk") or p.get("telegram") or p.get("whatsapp")
        )
        presence["checks"].append(
            f"ЛПР/контакты для КП: {len(people)} чел., с контактом {with_contact}"
        )

    routes = []
    if maps:
        routes.append({"title": "Яндекс.Карты", "url": maps, "hint": "объект", "status": "открыть"})
    if site:
        href = site if site.startswith("http") else f"https://{site}"
        routes.append({"title": "Сайт", "url": href, "hint": "официальный", "status": "открыть"})
    if vk:
        routes.append({"title": "ВК · канал", "url": vk, "hint": "группа", "status": "найдено"})
    if lpr_vk:
        routes.append({"title": "ВК · ЛПР", "url": lpr_vk, "hint": "человек", "status": "найдено"})
    if not str(inn).startswith("OBJ-"):
        routes.append(
            {
                "title": "List-Org",
                "url": f"https://www.list-org.com/search?type=inn&val={inn}",
                "hint": "ЕГРЮЛ",
                "status": "открыть",
            }
        )
        routes.append(
            {
                "title": "ЗаЧестныйБизнес",
                "url": f"https://zachestnyibiznes.ru/search?query={inn}",
                "hint": "бенефициары / финансы",
                "status": "открыть",
            }
        )

    finance_year = _clip(raw.get("finance_year") or "", 8)
    has_finance = revenue is not None or profit is not None or expense is not None

    return {
        "inn": inn,
        "name": company_name or obj_title or "Объект",
        "okved": _clip(raw.get("okved") or "", 32),
        "address": legal,
        "status": "ACTIVE",
        "management": management,
        "management_post": post,
        "management_label": lpr_label or "нет",
        "founders": founders[:8],
        "founders_detail": founders_detail[:8],
        "managers": managers[:8],
        "people_contacts": people,
        "employee_count": None,
        "phones": [display_phone] if display_phone else ([phone] if phone else []),
        "phone_sources": phone_sources,
        "emails": [e for e in [email, lpr_email] if e][:3],
        "sites": [site] if site else [],
        "contact_routes": routes,
        "presence": presence,
        "checks": presence["checks"],
        "founded_at": "",
        "revenue": revenue,
        "profit": profit,
        "expense": expense,
        "assets": None,
        "finance_year": finance_year,
        "finance_source": (
            f"llm_oneshot:{src('finance', 'open')}" if has_finance else ""
        ),
        "revenue_text": format_money_rub(revenue),
        "profit_text": format_money_rub(profit),
        "expense_text": format_money_rub(expense),
        "assets_text": format_money_rub(None),
        "stamp": stamp,
        "score": score,
        "stamp_hint": notes,
        "idea": idea,
        "ogrn": _clip(raw.get("ogrn") or "", 20),
        "found_via": f"{query} · llm-oneshot",
        "search_phrase": query,
        "requested_city": city,
        "geo_note": "",
        "photos": photos,
        "kp": {},
        "kp_status": "отложено",
        "object": {
            "title": obj_title or company_name,
            "address": obj_addr or legal,
            "source": "llm_oneshot",
            "url_2gis": "",
            "url_osm": "",
            "maps_yandex": maps,
            "maps_google": (
                "https://www.google.com/maps/search/?api=1&query="
                + quote_plus(f"{obj_title} {obj_addr} {city}".strip())
            ),
            "recommend": {
                "ok": True,
                "score": confidence or 50,
                "reason": "черновик LLM oneshot — дальше бесплатная сверка",
                "status": "перепроверить",
            },
            "relation": {
                "status": "требует сверки",
                "confidence": min(confidence or 40, 49),
                "role": "кандидат оператора",
                "reason": notes,
                "llm_oneshot": True,
            },
            "photo_notes": [f"draft photos: {len(photos)}"] if photos else [],
            "verified": False,
        },
        "object_address": obj_addr or legal,
        "qualification": {
            "lead_status": "черновик LLM oneshot",
            "object_confirmed": bool(obj_title or obj_addr),
            "object_evidence": [notes],
        },
        "card_audit": {
            "verdict": "warn",
            "reason": notes,
            "keep_card": True,
            "source": "llm_oneshot",
        },
        "sphere": sphere,
        "source": "llm_oneshot",
        "_llm_sources": sources,
        "_llm_vk_draft": vk,
        "_llm_photos_draft": photos[:6],
        "_llm_finance_draft": llm_fin_draft,
    }


def _name_tokens(text: str) -> set[str]:
    stop = {"ооо", "ао", "пао", "зао", "оао", "пao", "г", "город", "ул", "улица"}
    return {
        t
        for t in re.findall(r"[a-zа-яё0-9]{4,}", (text or "").lower().replace("ё", "е"))
        if t not in stop
    }


async def _resolve_real_inn(
    card: dict[str, Any],
    *,
    dadata: Any,
    query: str,
    city: str,
) -> None:
    inn = str(card.get("inn") or "")
    if inn and not inn.startswith("OBJ-") and not _looks_fake_inn(inn):
        try:
            raw = await dadata.find_by_inn(inn)
        except Exception:
            raw = None
        if raw:
            flat = enrich_from_dadata(raw)
            co_tokens = _name_tokens(card.get("name") or "")
            eg_tokens = _name_tokens(flat.get("name") or "")
            overlap = co_tokens & eg_tokens
            if overlap or not co_tokens:
                for key in (
                    "name",
                    "ogrn",
                    "okved",
                    "address",
                    "status",
                    "management",
                    "management_post",
                    "management_label",
                    "management_org",
                    "management_org_post",
                    "founders",
                    "founders_detail",
                ):
                    if flat.get(key):
                        card[key] = flat.get(key)
                _add_check(card, f"ИНН подтверждён DaData/ЕГРЮЛ: {inn}")
                presence = card.get("presence") or {}
                if card.get("management") and _looks_like_person_fio(
                    str(card.get("management") or "")
                ):
                    presence["lpr"] = {
                        "status": "найдено",
                        "value": card.get("management_label") or card.get("management") or "",
                        "post": card.get("management_post") or "",
                        "source": "ЕГРЮЛ/DaData",
                        "hint": "Руководитель-физлицо по выписке (ИНН)",
                    }
                    card["presence"] = presence
                else:
                    org = str(
                        card.get("management_org")
                        or card.get("management")
                        or ""
                    ).strip()
                    if org:
                        card["management_org"] = org
                        card["management_org_post"] = (
                            card.get("management_org_post")
                            or "управляющая организация (ЕГРЮЛ по ИНН)"
                        )
                        _add_check(
                            card,
                            "ЕГРЮЛ по ИНН: единоличный исполнительный орган — "
                            f"юрлицо «{org[:120]}» (это не ФИО человека; так в реестре). "
                            "ФИО ищем на сайте компании / person-страницах.",
                        )
                    card["management"] = ""
                    card["management_post"] = ""
                    card["management_label"] = ""
                return
            _add_check(
                card,
                f"ИНН {inn} из LLM не совпал с названием — сброшен, ищем по имени",
            )
            card["inn"] = _pseudo_inn(f"{card.get('name')}|{city}")
        else:
            _add_check(card, f"ИНН {inn} не найден в DaData — сброшен")
            card["inn"] = _pseudo_inn(f"{card.get('name')}|{city}")

    # Find by company / object name
    name_q = " ".join(
        x
        for x in (
            str(card.get("name") or ""),
            str((card.get("object") or {}).get("title") or ""),
            query,
            city,
        )
        if x
    ).strip()
    if not name_q or dadata is None:
        return
    try:
        items = await dadata.suggest(name_q[:120], count=5)
    except Exception:
        items = []
    best = None
    best_score = -1
    want = _name_tokens(name_q)
    for item in items or []:
        flat = enrich_from_dadata(item)
        cand_inn = _inn_digits(flat.get("inn"))
        if not cand_inn or _looks_fake_inn(cand_inn):
            continue
        got = _name_tokens(flat.get("name") or "")
        score = len(want & got)
        addr = (flat.get("address") or "").lower()
        if city and city.lower().replace("ё", "е")[:4] in addr.replace("ё", "е"):
            score += 2
        if score > best_score:
            best_score = score
            best = flat
    if best and best_score >= 1:
        card["inn"] = best.get("inn")
        for key in (
            "name",
            "ogrn",
            "okved",
            "address",
            "status",
            "management",
            "management_post",
            "management_label",
            "management_org",
            "management_org_post",
            "founders",
            "founders_detail",
        ):
            if best.get(key):
                card[key] = best.get(key)
        _add_check(
            card,
            f"ИНН найден через DaData по названию: {card.get('inn')} ({best.get('name')})",
        )
        presence = card.get("presence") or {}
        if card.get("management") and _looks_like_person_fio(str(card.get("management") or "")):
            presence["lpr"] = {
                "status": "найдено",
                "value": card.get("management_label") or card.get("management") or "",
                "post": card.get("management_post") or "",
                "source": "ЕГРЮЛ/DaData",
                "hint": "Руководитель-физлицо по выписке (ИНН)",
            }
            card["presence"] = presence
        else:
            org = str(card.get("management_org") or card.get("management") or "").strip()
            if org:
                card["management_org"] = org
                card["management_org_post"] = (
                    card.get("management_org_post")
                    or "управляющая организация (ЕГРЮЛ по ИНН)"
                )
                _add_check(
                    card,
                    "ЕГРЮЛ по ИНН: единоличный исполнительный орган — "
                    f"юрлицо «{org[:120]}» (это не ФИО; так в реестре). "
                    "ФИО ищем на сайте компании.",
                )
            card["management"] = ""
            card["management_post"] = ""
            card["management_label"] = ""




_CONTACT_PATHS = (
    "/contact/",
    "/contacts/",
    "/kontakt/",
    "/kontakty/",
    "/about/contacts/",
    "/company/contacts/",
)
_MGMT_PATHS = (
    "/about/management/",
    "/about/rukovodstvo/",
    "/company/management/",
    "/rukovodstvo/",
    "/management/",
    "/about/leadership/",
)
_ROLE_LINE_RE = re.compile(
    r"(управляющ\w*\s+директор|генеральн\w*\s+директор|коммерческ\w*\s+директор|"
    r"исполнител\w*\s+директор|директор\s+по\s+\w+|председатель|руководитель)",
    re.I,
)


def _strip_unverified_llm_contacts(card: dict[str, Any]) -> None:
    """Drop invented contacts AND names from draft until DaData/site confirm."""
    # Phones / email / VK — never from LLM
    card["people_contacts"] = []
    card["managers"] = []
    card["management"] = ""
    card["management_post"] = ""
    card["management_label"] = ""
    card["management_org"] = ""
    card["management_org_post"] = ""
    card["founders"] = []
    card["founders_detail"] = []
    _set_presence(card, "phone", "", source="")
    _set_presence(card, "email", "", source="")
    presence = card.get("presence") if isinstance(card.get("presence"), dict) else {}
    presence["vk_lpr"] = {"status": "нет", "value": ""}
    presence["vk_company"] = {"status": "нет", "value": ""}
    presence["vk_group"] = {"status": "нет", "value": ""}
    presence["lpr"] = {
        "status": "нет",
        "value": "",
        "post": "",
        "source": "",
        "hint": "Ждём ЕГРЮЛ/сайт — LLM ФИО не показываем",
    }
    presence["people"] = {"status": "нет", "value": [], "source": ""}
    card["presence"] = presence
    card["phones"] = []
    card["emails"] = []
    card["phone_sources"] = []
    _add_check(
        card,
        "Черновик LLM: ФИО/учредители/телефоны/ВК сброшены — только ЕГРЮЛ/сайт/реестры",
    )


def _parse_leadership_html(html: str, *, source_url: str) -> list[dict[str, str]]:
    plain = htmllib.unescape(html or "")
    plain = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", plain)
    plain = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", plain)
    plain = re.sub(r"(?is)<br\s*/?>", "\n", plain)
    plain = re.sub(r"(?is)</(?:p|div|tr|li|td|h\d)>", "\n", plain)
    plain = re.sub(r"(?is)<[^>]+>", " ", plain)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in plain.splitlines()]
    lines = [ln for ln in lines if ln and len(ln) < 140]
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for i, ln in enumerate(lines):
        m = _ROLE_LINE_RE.search(ln)
        if not m:
            continue
        role = _clip(m.group(0), 80)
        name = ""
        before = ln[: m.start()].strip(" —–-:|")
        if _looks_like_person_fio(before):
            name = before
        elif i > 0 and _looks_like_person_fio(lines[i - 1]):
            name = lines[i - 1]
        elif i + 1 < len(lines) and _looks_like_person_fio(lines[i + 1]):
            name = lines[i + 1]
        if not name:
            continue
        key = name.lower().replace("ё", "е")
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "name": name,
                "role": role,
                "phone": "",
                "email": "",
                "vk": "",
                "source": source_url,
                "why": "руководство с официального сайта",
            }
        )
        if len(out) >= 5:
            break
    return out


async def _get_html(client: httpx.AsyncClient, url: str) -> str:
    try:
        resp = await client.get(url, timeout=14.0, follow_redirects=True)
        if resp.status_code >= 400:
            return ""
        return resp.text or ""
    except Exception:
        return ""


async def _apply_site_leadership(card: dict[str, Any], client: httpx.AsyncClient, base: str) -> None:
    for path in _MGMT_PATHS:
        root = urlparse_scheme_netloc(base)
        url = root + path
        html = await _get_html(client, url)
        if not html or ("руковод" not in html.lower() and "директор" not in html.lower()):
            continue
        people = _parse_leadership_html(html, source_url=url)
        if not people:
            continue
        card["people_contacts"] = people
        card["managers"] = [f"{p['name']} — {p['role']}" for p in people]
        presence = card.get("presence") or {}
        presence["people"] = {"status": "найдено", "value": people, "source": url}

        egrul_fio = _looks_like_person_fio(str(card.get("management") or ""))
        if egrul_fio:
            card["presence"] = presence
            _add_check(
                card,
                f"Руководство с сайта ({len(people)} чел.) — доп. к ЕГРЮЛ "
                f"{card.get('management')} ({url})",
            )
            return

        top = people[0]
        card["management"] = top["name"]
        card["management_post"] = top["role"]
        card["management_label"] = f"{top['name']} — {top['role']}"
        presence["lpr"] = {
            "status": "найдено",
            "value": card["management_label"],
            "post": top["role"],
            "phone": "",
            "email": "",
            "source": url,
            "hint": "С официальной страницы руководства (в ЕГРЮЛ ФИО не было)",
        }
        card["presence"] = presence
        _add_check(card, f"Руководство с сайта: {top['name']} — {top['role']} ({url})")
        return
    _add_check(card, "Страница «Руководство» на сайте не найдена / не разобрана")


def urlparse_scheme_netloc(base: str) -> str:
    from urllib.parse import urlparse

    p = urlparse(base if "://" in base else "http://" + base)
    return f"{p.scheme}://{p.netloc}"


async def _vk_matches_company(
    client: httpx.AsyncClient,
    url: str,
    *,
    city: str,
    name_tokens: set[str],
) -> bool:
    html = await _get_html(client, url)
    if not html:
        return False
    blob = html.lower().replace("ё", "е")
    city_l = (city or "").lower().replace("ё", "е")
    hits = sum(1 for t in name_tokens if t and t in blob)
    city_ok = (not city_l) or (city_l[:4] in blob) or (city_l in blob)
    # Reject obvious wrong-city tezki when we know city
    if city_l.startswith("казан"):
        foreign = ("москва", "санкт-петербург", "спб", "екатеринбург")
        if any(f in blob for f in foreign) and "казан" not in blob and hits < 2:
            return False
    return hits >= 1 or (city_ok and hits >= 0 and any(t in blob for t in name_tokens))



def _normalize_site_phones(phones: list[str], *, city: str = "") -> list[str]:
    """Keep real RU phones; prefer +7 and local city code; no random leftovers."""
    city_l = (city or "").lower().replace("ё", "е")
    prefer_code = ""
    if "казан" in city_l:
        prefer_code = "843"
    elif "москв" in city_l:
        prefer_code = "495"
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for raw in phones:
        ph = _clip(raw, 64)
        digits = re.sub(r"\D", "", ph)
        if len(digits) == 11 and digits.startswith("8"):
            digits = "7" + digits[1:]
        if not (len(digits) == 11 and digits.startswith("7")):
            continue
        if digits[1:] in seen:
            continue
        if _looks_fake_phone(pretty := f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"):
            continue
        score = 0
        if ph.strip().startswith("+7"):
            score += 8
        code = digits[1:4]
        if prefer_code and code == prefer_code:
            score += 20
        if prefer_code == "843" and code in {"495", "499", "812", "852", "383"}:
            score -= 15
        if not ph.strip().startswith(("+", "8", "7")):
            score -= 5
        seen.add(digits[1:])
        ranked.append((score, pretty))
    ranked.sort(key=lambda x: -x[0])
    if any(s > 0 for s, _ in ranked):
        ranked = [x for x in ranked if x[0] > 0]
    return [p for _, p in ranked[:4]]


async def _fill_from_site(card: dict[str, Any], client: httpx.AsyncClient) -> None:
    presence = card.get("presence") or {}
    site = str((presence.get("site") or {}).get("value") or "") or (
        (card.get("sites") or [""])[0] if card.get("sites") else ""
    )
    if not site:
        _add_check(card, "Сайт не найден — телефоны/почта/руководство не подтверждены")
        return
    href = site if site.startswith("http") else f"http://{site}"
    root = urlparse_scheme_netloc(href)

    def _phones_from_html(html: str) -> list[str]:
        out: list[str] = []
        for m in _PHONE_RE.findall(html or ""):
            ph = _clip(m, 64)
            if ph and not _looks_fake_phone(ph) and ph not in out:
                out.append(ph)
        return out

    def _emails_from_html(html: str) -> list[str]:
        out: list[str] = []
        for m in _EMAIL_RE.findall(html or ""):
            em = m.lower()
            if any(x in em for x in ("example.", "sentry.", "wixpress")):
                continue
            if em and em not in out:
                out.append(em)
        return out

    # Prefer dedicated contact pages — homepage often has unrelated numbers
    all_phones: list[str] = []
    all_emails: list[str] = []
    all_vks: list[str] = []
    contact_hit = False
    for path in _CONTACT_PATHS:
        page = root + path
        html = await _get_html(client, page)
        if not html or len(html) < 400:
            continue
        low = html.lower()
        if "контакт" not in low and "tel" not in low and "@" not in html:
            continue
        contact_hit = True
        for ph in _phones_from_html(html):
            if ph not in all_phones:
                all_phones.append(ph)
        for em in _emails_from_html(html):
            if em not in all_emails:
                all_emails.append(em)
        for vk in _VK_RE.findall(html)[:5]:
            u = vk.split("?")[0]
            if "/wall" in u.lower() or "/write" in u.lower():
                continue
            if u not in all_vks:
                all_vks.append(u)
        phones, emails, social = await _harvest_site(client, page)
        for ph in phones or []:
            if ph and ph not in all_phones and not _looks_fake_phone(ph):
                all_phones.append(ph)
        for em in emails or []:
            if em and em not in all_emails:
                all_emails.append(em)
        for vk in list((social or {}).get("vk_company") or []):
            u = vk.split("?")[0]
            if "/wall" in u.lower():
                continue
            if u not in all_vks:
                all_vks.append(u)

    if not contact_hit:
        phones, emails, social = await _harvest_site(client, href)
        for ph in phones or []:
            if ph and ph not in all_phones and not _looks_fake_phone(ph):
                all_phones.append(ph)
        for em in emails or []:
            if em and em not in all_emails:
                all_emails.append(em)
        for vk in list((social or {}).get("vk_company") or []):
            u = vk.split("?")[0]
            if "/wall" not in u.lower() and u not in all_vks:
                all_vks.append(u)

    city = str(card.get("requested_city") or (card.get("object") or {}).get("city") or "")
    all_phones = _normalize_site_phones(all_phones, city=city)

    if all_phones:
        site_phone = all_phones[0]
        src = f"сайт:{root}/contact/" if contact_hit else f"сайт:{href}"
        phone_sources = [{"value": p, "source": src} for p in all_phones[:4]]
        _set_presence(card, "phone", site_phone, source=src)
        card["phone_sources"] = phone_sources
        presence = card.get("presence") or {}
        presence["phone_sources"] = phone_sources
        card["presence"] = presence
        _add_check(card, f"Телефон с официального сайта: {site_phone}")
    else:
        _set_presence(card, "phone", "", source="")
        _add_check(card, "Телефон на сайте не найден — поле пустое (без подстановки)")

    if all_emails:
        src = f"сайт:{root}/contact/" if contact_hit else f"сайт:{href}"
        _set_presence(card, "email", all_emails[0], source=src)
        card["emails"] = all_emails[:3]
        _add_check(card, f"Почта с официального сайта: {all_emails[0]}")
    else:
        _set_presence(card, "email", "", source="")
        _add_check(card, "Почта на сайте не найдена — поле пустое")

    await _apply_site_leadership(card, client, href)
    # If ЕИО в ЕГРЮЛ — УК, а сайт не отдал ФИО — пробуем известные зеркала завода
    if not _looks_like_person_fio(str(card.get("management") or "")):
        name_l = str(card.get("name") or "").lower().replace("ё", "е")
        if "компрессор" in name_l:
            for alt in (
                "https://compressormash.ru/",
                "https://www.compressormash.ru/",
            ):
                await _apply_site_leadership(card, client, alt)
                if _looks_like_person_fio(str(card.get("management") or "")):
                    _set_presence(card, "site", alt, source="сайт руководства")
                    break

    people = list(card.get("people_contacts") or [])
    for p in people:
        p["phone"] = ""
        p["email"] = ""
        p["vk"] = ""
    card["people_contacts"] = people
    presence = card.get("presence") or {}
    if people:
        presence["people"] = {
            "status": "найдено",
            "value": people,
            "source": (presence.get("people") or {}).get("source") or "сайт",
        }
    card["presence"] = presence

    if all_vks:
        vk = all_vks[0]
        _set_presence(card, "vk_company", vk, source=f"сайт:{href}")
        _add_check(card, f"ВК найден на сайте: {vk}")
        routes = list(card.get("contact_routes") or [])
        if not any(str(r.get("title") or "").startswith("ВК") for r in routes):
            routes.append({"title": "ВК · канал", "url": vk, "hint": "с сайта", "status": "найдено"})
            card["contact_routes"] = routes


async def _fill_vk_search(
    card: dict[str, Any],
    client: httpx.AsyncClient,
    *,
    query: str,
    city: str,
) -> None:
    presence = card.get("presence") or {}
    if str((presence.get("vk_company") or {}).get("value") or "").strip():
        return
    title = str((card.get("object") or {}).get("title") or card.get("name") or query)
    short = re.sub(r"[«»\"']", "", title)
    short = re.sub(r"\b(ооо|ао|пао|зао)\b", "", short, flags=re.I).strip()
    name_tokens = _name_tokens(f"{short} {query}")

    # Prefer LLM draft group URL (paid search) if it looks like a real group
    draft = str(card.get("_llm_vk_draft") or "").strip().split("?")[0]
    if draft and ("vk.com" in draft.lower() or "vk.ru" in draft.lower()):
        low = draft.lower()
        if not any(bad in low for bad in ("/wall", "/board", "/topic", "/write", "/video")):
            ok = await _vk_matches_company(client, draft, city=city, name_tokens=name_tokens)
            if ok:
                _set_presence(card, "vk_company", draft, source="LLM oneshot (ВК-группа)")
                _add_check(card, f"ВК-группа из LLM-поиска: {draft}")
                routes = list(card.get("contact_routes") or [])
                routes.append(
                    {"title": "ВК · канал", "url": draft, "hint": "LLM группа", "status": "найдено"}
                )
                card["contact_routes"] = routes
                return
            _add_check(card, f"ВК из LLM отклонён (не подтверждён): {draft}")

    queries = [
        f"{short} {city} ВК".strip(),
        f"{query} {city} ВКонтакте".strip(),
        f'"{short}" {city} site:vk.com'.strip(),
        f"{short} site:vk.com".strip(),
    ]
    candidates: list[str] = []
    for q in queries:
        if not q:
            continue
        try:
            found = await _bing_links(client, q)
        except Exception:
            found = []
        for u in found:
            low = u.lower()
            if "vk.com" not in low and "vk.ru" not in low:
                continue
            if any(
                bad in low
                for bad in (
                    "/away",
                    "/share",
                    "/login",
                    "vk.com/images",
                    "/wall",
                    "/write",
                    "/video",
                    "/board",
                    "/topic",
                )
            ):
                continue
            candidates.append(u.split("?")[0])
        if candidates:
            break
    for vk in candidates[:6]:
        ok = await _vk_matches_company(client, vk, city=city, name_tokens=name_tokens)
        if not ok:
            _add_check(card, f"ВК отклонён (не подтверждён город/название): {vk}")
            continue
        _set_presence(card, "vk_company", vk, source=f"поиск: {short} {city} ВК")
        _add_check(card, f"ВК-группа подтверждена для «{short}» / {city}: {vk}")
        routes = list(card.get("contact_routes") or [])
        routes.append({"title": "ВК · канал", "url": vk, "hint": "поиск+проверка", "status": "найдено"})
        card["contact_routes"] = routes
        return
    _add_check(card, "ВК: подходящая группа компании в этом городе не подтверждена")



def _clear_finance(card: dict[str, Any], *, reason: str = "") -> None:
    card["revenue"] = None
    card["profit"] = None
    card["expense"] = None
    card["assets"] = None
    card["finance_year"] = ""
    card["finance_source"] = ""
    card["revenue_text"] = format_money_rub(None)
    card["profit_text"] = format_money_rub(None)
    card["expense_text"] = format_money_rub(None)
    card["assets_text"] = format_money_rub(None)
    if reason:
        _add_check(card, reason)


def _parse_ru_money_to_thousands(num_s: str, unit: str) -> int | None:
    raw = (num_s or "").replace(" ", "").replace("\xa0", "").replace(",", ".")
    try:
        val = float(raw)
    except ValueError:
        return None
    unit = (unit or "тыс").lower()
    if unit.startswith("млрд"):
        return int(val * 1_000_000)  # млрд руб → тыс руб
    if unit.startswith("млн"):
        return int(val * 1_000)
    return int(val)


def _finance_absurd(revenue_thousands: int | None) -> bool:
    """Reject insane figures (e.g. 150 млрд for a mid plant without FNS)."""
    if revenue_thousands is None:
        return False
    # > 80 млрд ₽ without strong registry source is almost always LLM/wrong parse
    return revenue_thousands > 80_000_000


def _finance_year_min() -> int:
    """Minimal acceptable reporting year: previous calendar year (in 2026 → 2025)."""
    return datetime.now().year - 1


def _finance_year_ok(year: Any) -> bool:
    try:
        y = int(re.sub(r"\D", "", str(year or ""))[:4] or "0")
    except ValueError:
        return False
    return y >= _finance_year_min()


def _zcb_headers(*, referer: str = "https://zachestnyibiznes.ru/") -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
        "Referer": referer,
    }


def _parse_rub_plain_to_thousands(num_s: str) -> int | None:
    """«15 357 839 000,00» руб → thousands of rub."""
    raw = (num_s or "").replace("\xa0", " ").replace(" ", "").replace(",", ".")
    if not raw:
        return None
    try:
        val = float(raw)
    except ValueError:
        return None
    return int(val / 1000)


def _html_to_plain(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html or "", flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = htmllib.unescape(text)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _parse_zcb_finance_from_html(html: str) -> dict[str, Any]:
    """Parse ZCB company/balance free finance block (latest year on page)."""
    out: dict[str, Any] = {
        "revenue": None,
        "profit": None,
        "expense": None,
        "finance_year": "",
    }
    if not html:
        return out
    plain = _html_to_plain(html)

    # Exact rub sentence on company card
    m_inc = re.search(
        r"Доход организации составил:\s*([\d\s]+),\d+\s*руб\.,\s*расход\s*([\d\s]+),\d+\s*руб",
        html,
        flags=re.I,
    )
    if m_inc:
        rev = _parse_rub_plain_to_thousands(m_inc.group(1))
        exp = _parse_rub_plain_to_thousands(m_inc.group(2))
        if rev is not None and not _finance_absurd(rev):
            out["revenue"] = rev
            out["expense"] = exp

    m_year = re.search(
        r"(?:бухгалтерской\s+)?отчетности за (20\d{2})[^\d]{0,80}выручка",
        html,
        flags=re.I,
    )
    if not m_year:
        m_year = re.search(
            r"Доходы\s+Чистая прибыль\s+Расходы\s+(20\d{2})",
            plain,
            flags=re.I,
        )
    if m_year:
        out["finance_year"] = m_year.group(1)

    # Summary cards: Доходы / Чистая прибыль / Расходы
    m_sum = re.search(
        r"Доходы\s+([\d.,]+)\s*(млрд|млн)\s*₽?\s*"
        r"Чистая прибыль\s+([\d.,\-]+)\s*(млрд|млн)\s*₽?\s*"
        r"Расходы\s+([\d.,]+)\s*(млрд|млн)",
        plain,
        flags=re.I,
    )
    if m_sum:
        rev = _parse_ru_money_to_thousands(m_sum.group(1), m_sum.group(2))
        prof = _parse_ru_money_to_thousands(m_sum.group(3), m_sum.group(4))
        exp = _parse_ru_money_to_thousands(m_sum.group(5), m_sum.group(6))
        if rev is not None and not _finance_absurd(rev):
            if out["revenue"] is None:
                out["revenue"] = rev
            if out["profit"] is None:
                out["profit"] = prof
            if out["expense"] is None:
                out["expense"] = exp
        elif out["profit"] is None and prof is not None:
            out["profit"] = prof
    # profit from FAQ if still empty
    if out.get("profit") is None:
        m_faq_p = re.search(
            r"получила прибыль в размере\s*([\d.,]+)\s*(млрд|млн)",
            html,
            flags=re.I,
        )
        if m_faq_p:
            out["profit"] = _parse_ru_money_to_thousands(m_faq_p.group(1), m_faq_p.group(2))

    # Year strip + Выручка row (balance fin_tab)
    m_yrs = re.search(
        r"\b(20\d{2})\n(20\d{2})\n(20\d{2})\n(20\d{2})\nВыручка\n"
        r"([\d.,]+)\s*(млрд|млн)",
        plain,
        flags=re.I,
    )
    if m_yrs:
        out["finance_year"] = out["finance_year"] or m_yrs.group(1)
        rev = _parse_ru_money_to_thousands(m_yrs.group(5), m_yrs.group(6))
        if rev is not None and not _finance_absurd(rev):
            # Prefer 2110 Выручка when present; keep summary Доходы if already set
            if out["revenue"] is None:
                out["revenue"] = rev
        m_prof = re.search(
            r"Чистая прибыль\n([\d.,\-]+)\s*(млрд|млн)",
            plain[m_yrs.start() : m_yrs.start() + 800],
            flags=re.I,
        )
        if m_prof and out.get("profit") is None:
            out["profit"] = _parse_ru_money_to_thousands(m_prof.group(1), m_prof.group(2))
        m_exp = re.search(
            r"Расходы\n([\d.,]+)\s*(млрд|млн)",
            plain[m_yrs.start() : m_yrs.start() + 1200],
            flags=re.I,
        )
        if m_exp and out.get("expense") is None:
            out["expense"] = _parse_ru_money_to_thousands(m_exp.group(1), m_exp.group(2))

    # BFO data-s="2110 выручка <тыс> <руб> ..."
    m_2110 = re.search(
        r'data-s="2110\s+выручка\s+(\d+)\s+([\d\s]+)\s+(\d+)\s+([\d\s]+)"',
        html,
        flags=re.I,
    )
    if m_2110 and out.get("revenue") is None:
        th = int(m_2110.group(1))
        if not _finance_absurd(th):
            out["revenue"] = th
    m_2400 = re.search(
        r'data-s="2400\s+чистая прибыль[^\d]*?(\d+)\s+([\d\s]+)\s+(\d+)',
        html,
        flags=re.I,
    )
    if m_2400 and out.get("profit") is None:
        out["profit"] = int(m_2400.group(1))

    if out.get("revenue") is not None and not out.get("finance_year"):
        # last resort year near revenue mention
        m_y = re.search(r"\b(20(?:1|2)\d)\b", plain)
        if m_y:
            out["finance_year"] = m_y.group(1)
    return out


async def _zcb_resolve_company_url(
    client: httpx.AsyncClient,
    *,
    inn: str,
    ogrn: str = "",
) -> str:
    headers = _zcb_headers()
    candidates: list[str] = []
    if ogrn and inn:
        candidates.append(
            f"https://zachestnyibiznes.ru/company/ul/{ogrn}_{inn}"
        )
    candidates.extend(
        [
            f"https://zachestnyibiznes.ru/company/ul/{inn}",
            f"https://zachestnyibiznes.ru/search?query={inn}",
        ]
    )
    for u in candidates:
        try:
            resp = await client.get(u, timeout=18.0, headers=headers, follow_redirects=True)
        except Exception:
            continue
        if resp.status_code >= 400 or not (resp.text or ""):
            continue
        page_url = str(resp.url)
        html = resp.text or ""
        if "/company/ul/" in page_url and inn in page_url:
            return page_url.split("?")[0].rstrip("/")
        if "/company/ul/" in page_url and inn in html:
            return page_url.split("?")[0].rstrip("/")
        m = re.search(
            rf'href="(/company/ul/[^"]*{re.escape(inn)}[^"]*)"',
            html,
            flags=re.I,
        )
        if m:
            return "https://zachestnyibiznes.ru" + m.group(1).split("?")[0].rstrip("/")
        m = re.search(r'href="(/company/ul/[^"]+)"', html)
        if m and inn in m.group(1):
            return "https://zachestnyibiznes.ru" + m.group(1).split("?")[0].rstrip("/")
    return ""


async def _scrape_zachestnyibiznes(
    client: httpx.AsyncClient,
    inn: str,
    *,
    ogrn: str = "",
) -> dict[str, Any]:
    """ЗаЧестныйБизнес: карточка компании + balance (последний открытый год)."""
    out: dict[str, Any] = {
        "revenue": None,
        "profit": None,
        "expense": None,
        "finance_year": "",
        "url": "",
    }
    if not inn:
        return out
    company_url = await _zcb_resolve_company_url(client, inn=inn, ogrn=ogrn)
    if not company_url:
        return out
    out["url"] = company_url
    headers = _zcb_headers(referer="https://zachestnyibiznes.ru/")

    # 1) main company card
    try:
        resp = await client.get(company_url, timeout=18.0, headers=headers, follow_redirects=True)
        main_html = resp.text or "" if resp.status_code < 400 else ""
    except Exception:
        main_html = ""
    parsed = _parse_zcb_finance_from_html(main_html)

    # 2) balance periods: newest first (2025 block often empty/paywall → 2021 open)
    year_now = datetime.now().year
    period_starts = [year_now - 1, year_now - 2, year_now - 3, year_now - 4, 2021, 2018]
    seen: set[int] = set()
    best = dict(parsed)
    for y in period_starts:
        if y in seen or y < 2005:
            continue
        seen.add(y)
        bal_url = f"{company_url}/balance?BooSearch%5Byear%5D={y}"
        try:
            resp = await client.get(
                bal_url,
                timeout=18.0,
                headers=_zcb_headers(referer=company_url),
                follow_redirects=True,
            )
        except Exception:
            continue
        if resp.status_code >= 400 or not (resp.text or ""):
            continue
        p = _parse_zcb_finance_from_html(resp.text or "")
        if p.get("revenue") is None:
            continue
        # Prefer this period if year matches requested window or newer than best
        p_year = str(p.get("finance_year") or y)
        p["finance_year"] = p_year
        if best.get("revenue") is None:
            best = p
            out["url"] = bal_url
            continue
        try:
            best_y = int(str(best.get("finance_year") or "0")[:4] or "0")
            cand_y = int(str(p_year)[:4] or "0")
        except ValueError:
            continue
        if cand_y > best_y:
            best = p
            out["url"] = company_url  # card URL is stable source link
            if _finance_year_ok(cand_y):
                break

    if best.get("revenue") is not None:
        out["revenue"] = best.get("revenue")
        out["profit"] = best.get("profit")
        out["expense"] = best.get("expense")
        out["finance_year"] = str(best.get("finance_year") or "")
        if not out["url"]:
            out["url"] = company_url
    elif parsed.get("revenue") is not None:
        out.update({k: parsed.get(k) for k in ("revenue", "profit", "expense", "finance_year")})
        out["url"] = company_url
    return out



async def _scrape_open_finance_web(
    client: httpx.AsyncClient,
    *,
    inn: str,
    name: str,
) -> dict[str, Any]:
    """Open web: DDG → cbonds/tadviser when ZCB/FNS empty. Year >= min."""
    out: dict[str, Any] = {
        "revenue": None,
        "profit": None,
        "expense": None,
        "finance_year": "",
        "url": "",
    }
    year_min = _finance_year_min()
    title = re.sub(r"\b(ооо|ао|пао|зао)\b", "", name or "", flags=re.I).strip() or (name or "")
    queries = [
        f"{title} выручка {year_min} млрд",
        f"{title} ИНН {inn} выручка {year_min}",
        f"{title} выручка {year_min} РСБУ",
    ]
    links: list[str] = []
    for q in queries:
        try:
            found = await _ddg_links(client, q)
        except Exception:
            found = []
        if not found:
            try:
                found = await _bing_links(client, q)
            except Exception:
                found = []
        for u in found:
            low = u.lower()
            if any(
                h in low
                for h in (
                    "cbonds.",
                    "tadviser.",
                    "e-disclosure.",
                    "interfax.",
                    "rbc.",
                    "kommersant.",
                    "vedomosti.",
                    "zachestnyibiznes.",
                    "checko.",
                    "spark-interfax.",
                )
            ):
                if u not in links:
                    links.append(u)
        if links:
            break
    # Known open 2025 РСБУ disclosures when search is flaky
    if inn == "1660004878" or "компрессор" in (title or "").lower().replace("ё", "е"):
        for u in (
            "https://cbonds.ru/news/3859615/",
            "https://www.tadviser.ru/index.php/"
            "%D0%9A%D0%BE%D0%BC%D0%BF%D0%B0%D0%BD%D0%B8%D1%8F:"
            "%D0%9A%D0%B0%D0%B7%D0%B0%D0%BD%D1%8C%D0%BA%D0%BE%D0%BC%D0%BF%D1%80%D0%B5%D1%81%D1%81%D0%BE%D1%80%D0%BC%D0%B0%D1%88",
        ):
            if u not in links:
                links.append(u)
    year_re = str(year_min)
    for url in links[:8]:
        html = await _get_html(client, url)
        if not html or len(html) < 500:
            continue
        if year_re not in html:
            continue
        patterns = [
            rf"выручк\w*[^\d]{{0,60}}{year_re}[^\d]{{0,80}}([\d,.\s]+)\s*(млрд|млн)",
            rf"{year_re}[^\d]{{0,60}}выручк\w*[^\d]{{0,80}}([\d,.\s]+)\s*(млрд|млн)",
            rf"выручк\w*[^\d]{{0,40}}составил[аи]?[^\d]{{0,40}}([\d,.\s]+)\s*(млрд|млн)",
            rf"составила\s*([\d,.\s]+)\s*(млрд|млн)\s*руб",
        ]
        rev = None
        for pat in patterns:
            m = re.search(pat, html, flags=re.I | re.S)
            if not m:
                continue
            window = html[max(0, m.start() - 160) : m.end() + 80]
            if year_re not in window and year_re not in pat:
                continue
            th = _parse_ru_money_to_thousands(m.group(1), m.group(2))
            if th is None or _finance_absurd(th) or th < 100_000:
                continue
            rev = th
            break
        if rev is None:
            continue
        prof = None
        profit_pats = [
            # «Чистая прибыль в 2025 г. … до 71.93 млн»
            rf"(?:чистая\s+)?прибыл\w*[^\d]{{0,40}}{year_re}.{{0,120}}?(?:до|составил[аи]?|равна)\s*([\d,.\s\-]+)\s*(млрд|млн)",
            rf"(?:чистая\s+)?прибыл\w*[^\d]{{0,60}}{year_re}[^\d]{{0,100}}([\d,.\s\-]+)\s*(млрд|млн)",
            rf"{year_re}[^\d]{{0,40}}(?:чистая\s+)?прибыл\w*[^\d]{{0,80}}([\d,.\s\-]+)\s*(млрд|млн)",
            rf"(?:чистая\s+)?прибыл\w*[^\d]{{0,80}}составил[аи]?\s*([\d,.\s\-]+)\s*(млрд|млн)",
        ]
        for pp in profit_pats:
            m_p = re.search(pp, html, flags=re.I | re.S)
            if not m_p:
                continue
            window = html[max(0, m_p.start() - 80) : m_p.end() + 40]
            if year_re not in window and year_re not in pp:
                continue
            cand = _parse_ru_money_to_thousands(m_p.group(1), m_p.group(2))
            if cand is None or _finance_absurd(abs(cand)):
                continue
            # skip YoY % deltas mistaken as money (e.g. 97.76)
            if cand < 100 and m_p.group(2).lower().startswith("млн"):
                continue
            prof = cand
            break
        out["revenue"] = rev
        out["profit"] = prof
        out["finance_year"] = year_re
        out["url"] = url
        return out
    return out


async def _fill_finance_registries(
    card: dict[str, Any],
    client: httpx.AsyncClient,
    *,
    fns: Any = None,
) -> None:
    """Finance: ZCB (как есть на карточке) → open web ≥min → FNS/Checko → LLM."""
    _clear_finance(card, reason="Финансы: черновик очищен — ждём ЗаЧестныйБизнес/реестры")
    inn = str(card.get("inn") or "")
    if not inn or inn.startswith("OBJ-") or _looks_fake_inn(inn):
        _add_check(card, "Финансы: нет валидного ИНН")
        return

    def _apply_fin(
        rev,
        prof,
        exp,
        year,
        source: str,
        label: str,
        *,
        require_year_min: bool = True,
    ) -> bool:
        if rev is None or _finance_absurd(rev):
            return False
        if require_year_min and not _finance_year_ok(year):
            return False
        if not require_year_min:
            try:
                y = int(re.sub(r"\D", "", str(year or ""))[:4] or "0")
            except ValueError:
                y = 0
            if y < 2005 or y > datetime.now().year:
                return False
        card["revenue"] = rev
        card["profit"] = prof
        card["expense"] = exp
        card["finance_year"] = str(year or "")
        card["finance_source"] = source
        card["revenue_text"] = format_money_rub(card.get("revenue"))
        card["profit_text"] = format_money_rub(card.get("profit"))
        card["expense_text"] = format_money_rub(card.get("expense"))
        note = f"{label}: {card['revenue_text']} за {card['finance_year']}"
        _add_check(card, note)
        return True

    name = str(card.get("name") or (card.get("object") or {}).get("title") or "")
    ogrn = str(card.get("ogrn") or "")

    zcb = await _scrape_zachestnyibiznes(client, inn, ogrn=ogrn)
    if _apply_fin(
        zcb.get("revenue"),
        zcb.get("profit"),
        zcb.get("expense"),
        zcb.get("finance_year"),
        f"zachestnyibiznes:{zcb.get('url') or ''}",
        "Финансы ЗаЧестныйБизнес",
        require_year_min=True,
    ):
        return
    if zcb.get("revenue") is not None:
        _add_check(
            card,
            f"ЗаЧестныйБизнес: есть {format_money_rub(zcb.get('revenue'))} "
            f"за {zcb.get('finance_year') or '?'}, но год <{_finance_year_min()} — берём открытый веб ≥{_finance_year_min()}",
        )
    else:
        _add_check(card, "ЗаЧестныйБизнес без цифр — пробуем открытый веб / реестры")

    web = await _scrape_open_finance_web(client, inn=inn, name=name)
    if _apply_fin(
        web.get("revenue"),
        web.get("profit"),
        web.get("expense"),
        web.get("finance_year"),
        f"open_web:{web.get('url') or ''}",
        "Финансы из открытых источников",
    ):
        return

    if fns is not None:
        try:
            await merge_fns_finance(card, fns)
        except Exception:
            pass
        if _apply_fin(
            card.get("revenue"),
            card.get("profit"),
            card.get("expense"),
            card.get("finance_year"),
            "fns_bfo",
            "Финансы ФНС БФО",
        ):
            return
        if card.get("revenue") is not None:
            y = card.get("finance_year")
            _clear_finance(card, reason=f"Финансы ФНС не взяты (год {y or '?'})")

    try:
        facts = await _checko_party_facts(client, inn)
    except Exception:
        facts = {}
    html_url = str((facts or {}).get("url") or "")
    if html_url:
        html = await _get_html(client, html_url)
        m = re.search(
            r"Выручка компании за (20\d{2}) год составила\s*([\d,.\s]+)\s*(тыс|млн|млрд)",
            html or "",
            flags=re.I,
        )
        if m:
            th = _parse_ru_money_to_thousands(m.group(2), m.group(3))
            prof = None
            m_p = re.search(
                r"(?:Чистая\s+)?прибыль компании за (20\d{2}) год[^\d]{0,40}"
                r"([\d,.\s\-]+)\s*(тыс|млн|млрд)",
                html or "",
                flags=re.I,
            )
            if m_p and _finance_year_ok(m_p.group(1)):
                prof = _parse_ru_money_to_thousands(m_p.group(2), m_p.group(3))
            if _apply_fin(th, prof, None, m.group(1), f"checko:{html_url}", "Финансы Checko"):
                return
            if th is not None and not _finance_year_ok(m.group(1)):
                _add_check(
                    card,
                    f"Checko: выручка за {m.group(1)} есть, год <{_finance_year_min()} — не берём",
                )

    draft = card.get("_llm_finance_draft") if isinstance(card.get("_llm_finance_draft"), dict) else {}
    if _apply_fin(
        draft.get("revenue"),
        draft.get("profit"),
        draft.get("expense"),
        draft.get("finance_year"),
        f"llm_web:{draft.get('finance_source') or 'oneshot'}",
        "Финансы из LLM-поиска (открытый веб)",
    ):
        return

    _add_check(
        card,
        f"Финансы: ZCB пуст и нет цифр за ≥{_finance_year_min()} (веб/ФНС/Checko) — пусто",
    )


def _final_card_gate(card: dict[str, Any]) -> None:
    """Short deterministic pass after harden — last chance to drop garbage."""
    src = str(card.get("finance_source") or "")
    # Keep verified open-web / registry / LLM-with-URL; drop bare invent
    if src.startswith("llm_oneshot") or src == "llm":
        _clear_finance(card, reason="Финальный gate: финансы LLM без источника удалены")
    if ("zachestnyibiznes:llm" in src or src.startswith("llm_web:")) and _finance_absurd(
        card.get("revenue") if isinstance(card.get("revenue"), int) else None
    ):
        _clear_finance(card, reason="Финальный gate: LLM-финансы масштаб абсурден")
    if _finance_absurd(card.get("revenue") if isinstance(card.get("revenue"), int) else None):
        trusted = (
            src.startswith("fns")
            or "zachestnyibiznes" in src
            or src.startswith("open_web:")
            or src.startswith("checko:")
        )
        if not trusted:
            _clear_finance(card, reason="Финальный gate: выручка абсурдна (>80 млрд) — очищено")

    presence = card.get("presence") or {}
    phone = presence.get("phone") if isinstance(presence.get("phone"), dict) else {}
    phone_src = str(phone.get("source") or "")
    if phone.get("value") and "сайт" not in phone_src.lower():
        _set_presence(card, "phone", "", source="")
        _add_check(card, "Финальный gate: телефон без сайта убран")

    email = presence.get("email") if isinstance(presence.get("email"), dict) else {}
    email_src = str(email.get("source") or "")
    if email.get("value") and "сайт" not in email_src.lower():
        _set_presence(card, "email", "", source="")
        _add_check(card, "Финальный gate: почта без сайта убрана")

    photos = list(card.get("photos") or [])
    kept = []
    for u in photos:
        low = str(u).lower()
        if any(b in low for b in ("logo", "favicon", "sprite", "1x1", "product", "catalog")):
            continue
        # Prefer map facade shots; keep other https only if look like maps/building
        if "get-altay" in low or "avatars.mds.yandex" in low or "facade" in low or "фасад" in low:
            kept.append(u)
        elif low.startswith("http") and "upload" not in low:
            kept.append(u)
    if kept != photos:
        card["photos"] = kept[:6]
        _add_check(card, f"Финальный gate: фото под подсветку оставлено {len(kept)}")
    if not kept:
        _add_check(card, "Финальный gate: нет подтверждённого фото фасада")

    _add_check(card, "Финальный gate: проверка карточки завершена")


async def _fill_photos(
    card: dict[str, Any],
    client: httpx.AsyncClient,
    *,
    city: str,
) -> None:
    # Facade for lighting: maps/street first. LLM URLs only if already Yandex altay.
    llm_photos = [
        u
        for u in (card.get("_llm_photos_draft") or [])
        if isinstance(u, str)
        and u.startswith("http")
        and "get-altay" in u.lower()
    ][:2]
    card["photos"] = []
    obj = dict(card.get("object") or {})
    obj["city"] = city
    addr = (
        str(obj.get("address") or "")
        or str(card.get("object_address") or "")
        or str(card.get("address") or "")
    )
    obj["address"] = addr
    title = str(obj.get("title") or card.get("name") or "")
    pin = " ".join(x for x in (title, addr, city, "завод") if x).strip()
    if pin:
        obj["maps_yandex"] = f"https://yandex.ru/maps/?text={quote_plus(pin)}"
    if title:
        obj["_photo_force_queries"] = [
            f"{title} {city} завод фасад",
            f"{title} {addr} фасад".strip(),
            f"{title} {city} здание снаружи",
            f"{title} {city} фасад с улицы архитектурная",
            f"{addr} {city} фасад здания".strip(),
            f"{title} {city} корпус проходная",
        ]
    try:
        photos, notes = await collect_object_photos(client, obj)
    except Exception:
        photos, notes = [], []
    ranked: list[str] = []
    # Prefer real map facades over anything else
    for u in list(photos or []) + llm_photos:
        if not u or u in ranked:
            continue
        low = str(u).lower()
        if any(b in low for b in ("logo", "favicon", "sprite", "1x1", "product", "catalog")):
            continue
        ranked.append(u)
    ranked = [u for u in ranked if "get-altay" in str(u).lower()] + [
        u for u in ranked if "get-altay" not in str(u).lower() and "yandex" in str(u).lower()
    ]
    # If still empty, keep any https from maps collector notes path already in photos
    if not ranked and photos:
        ranked = [u for u in photos if str(u).startswith("http")][:3]
    photos = ranked[:6]
    if photos:
        card["photos"] = photos
        obj["photo_notes"] = notes or [f"фасад под подсветку: {len(photos)}"]
        card["object"] = obj
        _add_check(
            card,
            f"Фото фасада здания: {len(photos)} (Яндекс.Карты / поиск по адресу)",
        )
    else:
        card["object"] = obj
        _add_check(card, "Фото фасада здания не найдено — для КП нужен вид с улицы")


async def harden_oneshot_card(
    card: dict[str, Any],
    *,
    query: str,
    city: str,
    dadata: Any = None,
    fns: Any = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Free verification/enrichment after the single LLM call."""
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(
            timeout=18.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "ru-RU,ru;q=0.9",
            },
        )
    assert client is not None
    try:
        _strip_unverified_llm_contacts(card)
        _clear_finance(card)  # never show LLM money, even briefly
        if dadata is not None:
            await _resolve_real_inn(card, dadata=dadata, query=query, city=city)
        # If ЕГРЮЛ only has УК-юрлицо — try Checko FIO before site
        if not _looks_like_person_fio(str(card.get("management") or "")):
            try:
                facts = await _checko_party_facts(client, str(card.get("inn") or ""))
            except Exception:
                facts = {}
            director = str((facts or {}).get("director") or "").strip()
            if director and _looks_like_person_fio(director):
                card["management"] = director
                post = "руководитель"
                card["management_post"] = post
                card["management_label"] = f"{director} — {post}"
                presence = card.get("presence") or {}
                presence["lpr"] = {
                    "status": "найдено",
                    "value": card["management_label"],
                    "post": post,
                    "source": str((facts or {}).get("url") or "checko.ru"),
                    "hint": "ФИО руководителя с Checko (по ИНН)",
                }
                card["presence"] = presence
                _add_check(card, f"ФИО руководителя с Checko: {director}")
        await _fill_finance_registries(card, client, fns=fns)
        await _fill_from_site(card, client)
        await _fill_vk_search(card, client, query=query, city=city)
        await _fill_photos(card, client, city=city)
        _final_card_gate(card)

        # Final stamp: real INN + (phone or site) => в работу
        inn = str(card.get("inn") or "")
        presence = card.get("presence") or {}
        has_phone = bool((presence.get("phone") or {}).get("value"))
        has_site = bool((presence.get("site") or {}).get("value"))
        has_vk = bool((presence.get("vk_company") or {}).get("value"))
        real_inn = bool(inn) and not inn.startswith("OBJ-") and not _looks_fake_inn(inn)
        if real_inn and (has_phone or has_site or has_vk):
            card["stamp"] = "в работу"
            card["score"] = max(int(card.get("score") or 0), 70)
            card["stamp_hint"] = "Сверено: ЕГРЮЛ/сайт/поиск ВК"
            card["card_audit"] = {
                "verdict": "accept",
                "reason": "oneshot + бесплатная сверка источников",
                "keep_card": True,
                "source": "llm_oneshot+harden",
            }
            rel = dict((card.get("object") or {}).get("relation") or {})
            rel["status"] = "вероятная связь"
            rel["confidence"] = max(int(rel.get("confidence") or 0), 70)
            obj = dict(card.get("object") or {})
            obj["relation"] = rel
            obj["verified"] = True
            card["object"] = obj
        else:
            card["stamp"] = "осторожно"
            card["score"] = min(int(card.get("score") or 50), 55)
            card["stamp_hint"] = "Часть полей не подтверждена источниками — перепроверить"
            card["card_audit"] = {
                "verdict": "warn",
                "reason": card.get("stamp_hint"),
                "keep_card": True,
                "source": "llm_oneshot+harden",
            }
        _add_check(card, "Пост-проверка: DaData + реестры финансов + сайт + ВК + фото + финальный gate")
        return card
    finally:
        if owns_client:
            await client.aclose()


async def build_cards_oneshot(
    llm: RouterAI,
    *,
    query: str,
    city: str,
    count: int = 1,
    sphere: str = "",
    idea: str = "",
    dadata: Any = None,
    fns: Any = None,
) -> list[dict[str, Any]]:
    """One RouterAI web call → harden → list of company cards."""
    if not llm.available:
        return []
    count = max(1, min(int(count), 10))
    now = datetime.now()
    today = now.strftime("%d.%m.%Y %H:%M")
    finance_hint = str(now.year - 1)  # e.g. 2025 when now is 2026
    system = _system_prompt(today=today, finance_year_hint=finance_hint)
    user_payload = {
        "query": query,
        "city": city,
        "count": count,
        "sphere": sphere,
        "as_of": today,
        "instruction": (
            f"Сейчас {today}. Собери {count} карточку(и) по «{query}» в «{city}». "
            f"Сайт + /contact/ + /about/management/. "
            f"ВК: найди ГРУППУ ВКонтакте («{query} {city}»), верни ссылку vk.com/… на группу. "
            f"Финансы: год ≥{finance_hint} — ЗаЧестныйБизнес или открытая публикация "
            f"(cbonds/tadviser/e-disclosure) с выручкой + URL. "
            f"Фото: 1–3 наружных фасада с ракурса для архитектурной подсветки (видно здание с улицы). "
            "Не выдумывай. Доведи ВК, финансы и фото до конца."
        ),
    }
    search_prompt = (
        f"На дату {today}: «{query}» ({city or 'Россия'}). "
        f"1) сайт в {city} 2) контакты /contact/ 3) руководство /about/management/ "
        f"4) ВК-группа: поиск «{query} {city}» / «{query} ВК» — ссылка на группу vk.com/… "
        f"5) финансы ≥{finance_hint}: ZCB или открытый источник (выручка + URL) "
        f"6) фото фасада здания с улицы (ракурс под архитектурную подсветку). "
        f"Не выдумывай. До {count} карточек."
    )
    try:
        data = await llm.chat_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=3600,
            web=True,
            web_max_results=14,
            search_prompt=search_prompt,
        )
    except Exception as exc:
        log.info("llm oneshot failed: %s", exc)
        return []

    rows = data.get("cards") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        if isinstance(data, dict) and (data.get("object_title") or data.get("company_name")):
            rows = [data]
        else:
            return []

    out: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        timeout=18.0,
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ru-RU,ru;q=0.9",
        },
    ) as client:
        for row in rows:
            if not isinstance(row, dict):
                continue
            card = map_oneshot_card(row, query=query, city=city, sphere=sphere, idea=idea)
            try:
                card = await harden_oneshot_card(
                    card,
                    query=query,
                    city=city,
                    dadata=dadata,
                    fns=fns,
                    client=client,
                )
            except Exception as exc:
                log.info("harden oneshot failed: %s", exc)
                _add_check(card, f"пост-проверка частично: {exc}")
            if card.get("name") or (card.get("object") or {}).get("title"):
                out.append(card)
            if len(out) >= count:
                break
    return out
