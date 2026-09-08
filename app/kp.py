from __future__ import annotations

import json
import logging
from typing import Any

from app.llm import RouterAI
from app.spheres import SPHERES

log = logging.getLogger(__name__)

SYSTEM = """Ты коммерческий инженер Нiteos (LED-освещение для объектов B2B в России).
По карточке компании составь черновик КП — коротко, по делу, без воды.

Линейки (ориентир):
- Ритейл / магазины: NT-park, панели, крыльцо, зал
- Склады / логистика: NT-TOP, промышленный IP65, двор NT-WAY
- Промка / цеха: NT-PROM, NT-ЛУЧ, пролёт, пыль
- Прачечные / влага: IP65, линейный промышленный
- АЗС: NT-WAY навес, Ex-линейка
- Коммерческие здания: архитектурная подсветка фасада, входной группы, вывески,
  периметра и декоративных линий

Ответь строго JSON:
{
  "title": "заголовок КП",
  "object_type": "тип объекта одной фразой",
  "problem": "что у них болит по освещению",
  "offer": "что предлагаем Нiteos",
  "products": ["линейка 1", "линейка 2"],
  "benefits": ["выгода 1", "выгода 2", "выгода 3"],
  "first_step": "следующий шаг для менеджера",
  "message_short": "2-3 предложения — текст первого сообщения клиенту"
}
Используй только факты из карточки; если данных мало — общее КП под тип объекта по ОКВЭД/сфере."""


def _ctx(party: dict[str, Any]) -> dict[str, Any]:
    presence = party.get("presence") or {}
    vk_group = presence.get("vk_group") or {}
    return {
        "name": party.get("name"),
        "inn": party.get("inn"),
        "okved": party.get("okved"),
        "address": party.get("address"),
        "sphere": party.get("sphere"),
        "idea": party.get("idea"),
        "object_hint": (presence.get("object_hint") or {}).get("value"),
        "revenue": party.get("revenue_text") or party.get("revenue"),
        "employee_count": party.get("employee_count"),
        "vk_group": vk_group.get("value") or (presence.get("vk_company") or {}).get("value"),
        "vk_group_title": vk_group.get("title"),
        "vk_contacts": vk_group.get("contacts") or [],
        "phone": (presence.get("phone") or {}).get("value"),
        "email": (presence.get("email") or {}).get("value"),
        "site": (presence.get("site") or {}).get("value"),
        "photos": party.get("photos") or (presence.get("photos") or {}).get("value") or [],
        "architecture": (party.get("qualification") or {}).get("architecture") or {},
    }


async def generate_kp(llm: RouterAI, party: dict[str, Any]) -> dict[str, Any]:
    """Agent: draft KP from parsed company dossier."""
    if not llm.available:
        return {}
    sphere_id = str(party.get("sphere") or "")
    sphere = SPHERES.get(sphere_id)
    hint = sphere.idea if sphere else (party.get("idea") or "")
    user = {"company": _ctx(party), "niteos_line_hint": hint}
    try:
        data = await llm.chat_json(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=900,
        )
    except Exception as exc:
        log.warning("generate_kp failed: %s", exc)
        return {}
    if not isinstance(data, dict):
        return {}
    return data
