from __future__ import annotations

import logging

from aiogram import BaseMiddleware, Bot, Dispatcher, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonCommands,
    MenuButtonWebApp,
    Message,
    TelegramObject,
    WebAppInfo,
)

from app.access import DENY_TEXT, access_enabled, is_allowed
from app.config import Settings
from app import db
from app.fsm_storage import SqliteStorage

log = logging.getLogger(__name__)
router = Router()


def _app_url(bot: Bot) -> str:
    url = (getattr(bot, "webapp_url", "") or "").rstrip("/")
    token = getattr(bot, "webapp_token", "") or ""
    if url and token and "t=" not in url:
        url = f"{url}{'&' if '?' in url else '?'}t={token}"
    return url


def _open_kb(url: str) -> InlineKeyboardMarkup:
    https = url.startswith("https://")
    if https:
        button = InlineKeyboardButton(text="Открыть охоту", web_app=WebAppInfo(url=url))
    else:
        button = InlineKeyboardButton(text="Открыть охоту", url=url)
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


class TeamOnlyMiddleware(BaseMiddleware):
    """Block everyone except ALLOWED_USER_IDS. /id always works."""

    async def __call__(self, handler, event: TelegramObject, data: dict):
        settings: Settings = data["settings"]
        if not access_enabled(settings):
            return await handler(event, data)
        message = event if isinstance(event, Message) else getattr(event, "message", None)
        user = data.get("event_from_user")
        if user is None and isinstance(event, Message):
            user = event.from_user
        text = (getattr(message, "text", None) or "").strip()
        if text.startswith("/id") or text.startswith("/whoami"):
            return await handler(event, data)
        if user is None:
            return None
        if is_allowed(settings, user.id):
            return await handler(event, data)
        if isinstance(event, Message):
            await event.answer(f"{DENY_TEXT}\n\nТвой Telegram ID: `{user.id}`")
        return None


@router.message(Command("id"))
@router.message(Command("whoami"))
async def show_id(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    await message.answer(
        f"Твой Telegram ID: `{uid}`\n"
        "Передай его админу — добавят в ALLOWED_USER_IDS."
    )


@router.message(CommandStart())
async def start(message: Message, bot: Bot) -> None:
    url = _app_url(bot)
    if not url:
        await message.answer(
            "Мини-приложение ещё поднимается. Подожди 10 секунд и нажми /start ещё раз."
        )
        return
    await message.answer(
        "Охота Нитеос\n\n"
        "Открой приложение: город или вся Россия, ОКВЭД из списка или свой код, "
        "сколько компаний. Нажал «Начать охоту» — агенты сами ищут и проверяют, "
        "на экране готовый список.",
        reply_markup=_open_kb(url),
    )


@router.message(Command("base"))
async def show_base(message: Message, database) -> None:
    n = await db.company_count(database)
    await message.answer(f"В базе {n} компаний. Повторно агент 1 их не берёт.")


async def build_dispatcher(settings: Settings, database) -> Dispatcher:
    dp = Dispatcher(storage=SqliteStorage(settings.db_path))
    dp["settings"] = settings
    dp["database"] = database
    dp.message.middleware(TeamOnlyMiddleware())
    dp.include_router(router)
    return dp


async def run_polling(settings: Settings, database, bot: Bot | None = None) -> None:
    session = None
    own_session = False
    if bot is None:
        if settings.telegram_proxy:
            session = AiohttpSession(proxy=settings.telegram_proxy)
            log.info("telegram proxy %s", settings.telegram_proxy)
            own_session = True
        bot = Bot(settings.bot_token, session=session)
        bot.webapp_url = settings.webapp_url
        bot.webapp_token = settings.webapp_token
    dp = await build_dispatcher(settings, database)
    log.info("polling access=%s", "open" if not settings.allowed_user_ids else sorted(settings.allowed_user_ids))
    try:
        await dp.start_polling(bot)
    finally:
        await dp.storage.close()
        if own_session:
            await bot.session.close()


async def publish_webapp(bot: Bot, url: str) -> None:
    url = url.rstrip("/")
    bot.webapp_url = url
    if url.startswith("https://"):
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Охота", web_app=WebAppInfo(url=url))
        )
    else:
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    log.info("webapp menu %s", url)
