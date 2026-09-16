from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    app_name: str = "NITEOS Hunt V5"
    demo_mode: bool = False
    database_url: str = "sqlite:///./data/niteos_hunt.db"
    user_agent: str = "NITEOS-Hunt-V5/1.0"
    dadata_api_key: str = ""
    dadata_secret_key: str = ""
    cadastre_api_url: str = ""
    cadastre_api_key: str = ""
    public_search_api_url: str = ""
    public_search_api_key: str = ""
    public_image_search_api_url: str = ""
    public_image_search_api_key: str = ""
    yandex_maps_api_key: str = ""
    twogis_api_key: str = ""
    # LLM: RouterAI (OpenAI-compatible) preferred; OpenAI direct as fallback
    routerai_api_key: str = ""
    router_api_key: str = ""  # alias from main Niteos .env
    routerai_base_url: str = "https://routerai.ru/api/v1"
    routerai_model: str = "openai/gpt-4o-mini"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_reasoning_effort: str = "medium"
    llm_enabled: bool = False
    yandex_ai_api_key: str = ""
    yandex_ai_folder_id: str = ""
    yandex_ai_model: str = "yandexgpt"
    yandex_vision_enabled: bool = False
    sales_hide_people_without_contacts: bool = True
    model_config = SettingsConfigDict(
        env_file=str(_ROOT / ".env"),
        extra="ignore",
    )

    @property
    def llm_api_key(self) -> str:
        return (self.routerai_api_key or self.router_api_key or self.openai_api_key or "").strip()

    @property
    def llm_base_url(self) -> str:
        if (self.routerai_api_key or self.router_api_key or "").strip():
            return (self.routerai_base_url or "https://routerai.ru/api/v1").rstrip("/")
        return (self.openai_base_url or "https://api.openai.com/v1").rstrip("/")

    @property
    def llm_model(self) -> str:
        if (self.routerai_api_key or self.router_api_key or "").strip():
            return self.routerai_model or "openai/gpt-4o-mini"
        return self.openai_model or "gpt-4o-mini"

settings = Settings()
