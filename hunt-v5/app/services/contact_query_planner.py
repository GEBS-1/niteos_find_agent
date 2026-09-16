from __future__ import annotations

import json
import re

import httpx

from app.config import settings


def _fallback_queries(full_name: str, company: str, role: str, city: str) -> list[str]:
    role_text = role.replace("_", " ")
    return [
        f'"{full_name}" "{company}" телефон',
        f'"{full_name}" "{company}" мобильный',
        f'"{full_name}" "{company}" WhatsApp',
        f'"{full_name}" "{company}" MAX мессенджер',
        f'"{full_name}" "{company}" почта',
        f'"{full_name}" "{company}" email',
        f'"{full_name}" "{role_text}" "{city}"',
        f'"{full_name}" директор телефон',
        f'"{full_name}" владелец телефон',
        f'"{full_name}" site:vk.com',
        f'"{full_name}" site:ok.ru',
        f'"{full_name}" site:instagram.com',
        f'"{full_name}" site:t.me',
        f'"{full_name}" site:tenchat.ru',
        f'"{full_name}" site:max.ru',
        f'"{full_name}" filetype:pdf',
    ]


class LlmContactQueryPlanner:
    """Cheap LLM-assisted query expansion.

    The LLM only proposes search queries. It is never treated as a source for
    contacts, roles, ownership or cadastre.
    """

    async def queries_for_person(
        self, *, full_name: str, company: str, role: str, city: str
    ) -> list[str]:
        base = _fallback_queries(full_name, company, role, city)
        if not settings.llm_enabled or not settings.llm_api_key:
            return base[:16]
        prompt = (
            "Сформируй до 8 поисковых запросов для поиска публичных рабочих контактов "
            "конкретного человека. Нельзя придумывать контакты. Верни только JSON: "
            "{\"queries\":[\"...\"]}. Запросы должны искать телефон, email, Telegram/VK/WhatsApp, "
            "страницы PDF/DOCX, страницы компании, конференции, закупки, вакансии, СМИ, MAX. "
            f"Человек: {full_name}. Компания: {company}. Роль: {role}. Город: {city}."
        )
        payload = {
            "model": settings.llm_model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "Ты генерируешь только поисковые запросы."},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.post(
                    f"{settings.llm_base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(re.sub(r"^```(?:json)?|```$", "", content.strip()))
            queries = [str(x).strip() for x in data.get("queries") or [] if str(x).strip()]
        except Exception:
            queries = []
        out: list[str] = []
        seen: set[str] = set()
        for query in [*base, *queries]:
            key = query.lower().replace("ё", "е")
            if key in seen:
                continue
            seen.add(key)
            out.append(query)
            if len(out) >= 16:
                break
        return out
