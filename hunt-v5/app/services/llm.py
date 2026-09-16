from __future__ import annotations

import json
import re

import httpx

from app.config import settings


class OpenAIProposalEngine:
    """LLM only AFTER factual card is assembled (RouterAI / OpenAI-compatible).

    May analyze facade + write proposal. Must not invent ownership/contacts/cadastre/people.
    """

    async def build(self, *, card: dict, photo_url: str = "") -> dict:
        if not settings.llm_enabled or not settings.llm_api_key:
            return {"status": "not_configured", "analysis": "", "proposal": ""}

        facts = json.dumps(card, ensure_ascii=False, indent=2)
        instructions = (
            "Ты коммерческий инженер по архитектурному освещению. "
            "Работай ТОЛЬКО с фактами из карточки. Не придумывай собственников, телефоны, "
            "должности, площади или кадастровые данные. По фотографии оцени только видимые "
            "архитектурные особенности фасада и предложи концепцию подсветки. Затем напиши "
            "короткое персональное коммерческое обращение к наиболее релевантному ЛПР. "
            "Если ЛПР или прямой контакт не подтвержден, прямо это укажи. "
            "Верни JSON с полями facade_analysis, lighting_idea, proposal, risks."
        )
        user_text = f"Фактическая карточка:\n{facts}"
        if photo_url:
            user_text += f"\n\nФото/панорама фасада (URL, не выдумывай содержимое): {photo_url}"

        payload = {
            "model": settings.llm_model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_text},
            ],
        }
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{settings.llm_base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()

        text = ""
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except Exception:
            text = json.dumps(data, ensure_ascii=False)
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {
                "facade_analysis": text,
                "lighting_idea": "",
                "proposal": "",
                "risks": [],
            }
        if not isinstance(parsed, dict):
            parsed = {"facade_analysis": str(parsed), "lighting_idea": "", "proposal": "", "risks": []}
        parsed["status"] = "completed"
        parsed["model"] = settings.llm_model
        parsed["provider"] = "routerai" if "routerai" in settings.llm_base_url else "openai"
        return parsed
