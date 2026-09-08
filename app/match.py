from __future__ import annotations

import re
from typing import Iterable

# Юр. лица сетей часто не содержат бренд в названии — расширяем поиск и проверку.
BRAND_ALIASES: dict[str, tuple[str, ...]] = {
    "пятёрочка": ("пятёрочка", "пятерочка", "агроторг", "икс 5", "x5", "x5 retail"),
    "пятерочка": ("пятёрочка", "пятерочка", "агроторг", "икс 5", "x5"),
    "магнит": ("магнит", "тандер"),
    "перекрёсток": ("перекрёсток", "перекресток", "x5", "икс 5"),
    "перекресток": ("перекрёсток", "перекресток", "x5", "икс 5"),
    "лента": ("лента", "lenta"),
    "ашан": ("ашан", "auchan"),
    "дикси": ("дикси", "dixy"),
    "fix price": ("fix price", "фикс прайс", "фикспрайс"),
    "фикс прайс": ("fix price", "фикс прайс", "фикспрайс"),
    "фикспрайс": ("fix price", "фикс прайс", "фикспрайс"),
    "ozon": ("озон", "ozon", "интернет решения"),
    "озон": ("озон", "ozon", "интернет решения"),
}

_GENERIC_PHRASE = {
    "магазин",
    "магазины",
    "склад",
    "склады",
    "прачечная",
    "прачечные",
    "завод",
    "цех",
    "производство",
    "логистика",
    "продуктовый",
    "организация",
    "компания",
    "здание",
    "здания",
    "комплекс",
    "жилой",
    "офис",
    "офисное",
    "бизнес",
    "центр",
    "терминал",
    "площадка",
    "объект",
    "фасад",
    "парк",
    "парковка",
    "улица",
    "двор",
    "школа",
    "больница",
    "стадион",
    "бассейн",
    "азс",
    "заправка",
    "химчистка",
    "торговый",
    "гостиница",
    "отель",
}


def _yo(s: str) -> str:
    return (s or "").replace("ё", "е").replace("Ё", "Е")


def normalize_text(text: str) -> str:
    text = _yo((text or "").strip().lower())
    text = re.sub(r"\s+", " ", text)
    return text


def phrase_tokens(phrase: str) -> list[str]:
    out: list[str] = []
    for token in re.split(r"[^\wА-Яа-яЁё0-9]+", normalize_text(phrase)):
        if len(token) < 2 or token in _GENERIC_PHRASE:
            continue
        out.append(token)
    return out


def _brand_keys(phrase: str) -> list[str]:
    norm = normalize_text(phrase)
    keys: list[str] = []
    for key in BRAND_ALIASES:
        if key in norm:
            keys.append(key)
    for token in phrase_tokens(phrase):
        if token in BRAND_ALIASES and token not in keys:
            keys.append(token)
    return keys


def is_brand_query(phrase: str) -> bool:
    """True when the phrase names a known chain brand."""
    return bool(_brand_keys(phrase))


def expand_phrase_queries(phrase: str) -> list[str]:
    """Extra DaData queries for well-known retail / chain brands."""
    base = phrase.strip()
    if not base:
        return []
    out = [base]
    keys = _brand_keys(base)
    seen = {normalize_text(base)}
    for key in keys:
        for alias in BRAND_ALIASES.get(key, ()):
            if alias in _GENERIC_PHRASE:
                continue
            q = alias
            if normalize_text(q) not in seen:
                seen.add(normalize_text(q))
                out.append(q)
    return out


def _needles_for_phrase(phrase: str) -> list[str]:
    needles: list[str] = []
    seen: set[str] = set()
    for token in phrase_tokens(phrase):
        if token not in seen:
            seen.add(token)
            needles.append(token)
    for key in _brand_keys(phrase):
        for alias in BRAND_ALIASES.get(key, ()):
            norm = normalize_text(alias)
            if norm not in seen:
                seen.add(norm)
                needles.append(norm)
    return needles


def matches_phrase(company_name: str, phrase: str) -> bool:
    """True if company name relates to user phrase (incl. brand aliases)."""
    if not phrase.strip():
        return True
    name = normalize_text(company_name)
    if not name:
        return False
    needles = _needles_for_phrase(phrase)
    if not needles:
        # Only generic words like «магазин» — do not filter by name.
        return True
    return any(n in name for n in needles)


def matches_search_intent(
    company_name: str,
    phrase: str,
    *,
    okved: str = "",
    okved_prefixes: Iterable[str] = (),
) -> bool:
    """
    Company must match phrase (if any) and OKVED filter (if any).
    Phrase match can waive OKVED when brand alias hits (Пятёрочка ↔ Агроторг).
    """
    prefixes = [p for p in okved_prefixes if p]
    okved_ok = True
    if prefixes:
        code = (okved or "").strip()
        okved_ok = bool(code) and any(
            code.startswith(p) or p.startswith(code) for p in prefixes
        )
    if not phrase.strip():
        return okved_ok
    name_hit = matches_phrase(company_name, phrase)
    if not name_hit:
        return False
    if not prefixes:
        return True
    if okved_ok:
        return True
    # Brand/legal-name mismatch: accept if phrase strongly identifies the brand.
    return bool(_brand_keys(phrase))
