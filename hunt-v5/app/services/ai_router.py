from __future__ import annotations
from dataclasses import dataclass
from app.config import settings

@dataclass(frozen=True)
class AIPlan:
    provider: str
    model: str
    purpose: str
    enabled: bool


def current_ai_plan() -> list[AIPlan]:
    """Model routing for the prototype. Factual extraction stays deterministic/provider-based."""
    router_on = bool(settings.llm_enabled and (settings.routerai_api_key or settings.router_api_key))
    openai_on = bool(settings.llm_enabled and settings.openai_api_key and not router_on)
    return [
        AIPlan(
            "routerai",
            settings.routerai_model,
            "facade + proposal via OpenAI-compatible RouterAI (switchable)",
            router_on,
        ),
        AIPlan(
            "openai",
            settings.openai_model,
            "facade vision + proposal + source synthesis",
            openai_on,
        ),
        AIPlan(
            "yandex",
            settings.yandex_ai_model,
            "optional RU text synthesis / domestic fallback",
            bool(settings.yandex_ai_api_key and settings.llm_enabled),
        ),
        AIPlan(
            "yandex_vision",
            "vision-ocr",
            "OCR for PDFs/images when source text is unavailable",
            bool(settings.yandex_vision_enabled),
        ),
    ]


def factual_tasks() -> list[str]:
    return [
        "map/building search",
        "coordinates",
        "cadastre resolution",
        "owner/company lookup",
        "ownership graph",
        "person-contact attribution",
        "contact confidence scoring",
    ]
