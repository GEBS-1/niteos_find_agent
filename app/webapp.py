from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from aiohttp import web

from app.access import DENY_TEXT, access_enabled, is_allowed
from app.agents import run_hunt
from app.config import ROOT, Settings
from app import db
from app.db import connect
from app.geo_tree import geo_payload, parse_geo_selection
from app.okved import all_codes, title_for
from app.share_auth import (
    STAFF_UID,
    clear_session_cookie,
    make_guest_session,
    make_staff_session,
    new_share_token,
    password_ok,
    set_session_cookie,
    verify_session,
    session_secret,
)
from app.spheres import SPHERES
from app.telegram_web import parse_init_data

log = logging.getLogger(__name__)
WEB_DIR = ROOT / "web"


class HuntRuntime:
    def __init__(self, settings: Settings, database) -> None:
        self.settings = settings
        self.database = database
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.webapp_url = (settings.webapp_url or "").rstrip("/")


def _client_ip(request: web.Request) -> str:
    for header in ("CF-Connecting-IP", "True-Client-IP", "X-Real-IP"):
        raw = (request.headers.get(header) or "").strip()
        if raw:
            return raw.split(",")[0].strip()
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or (request.remote or "")


def _session_from_request(request: web.Request) -> dict[str, Any] | None:
    settings: Settings = request.app["runtime"].settings
    secret = session_secret(settings)
    raw = (
        request.headers.get("X-Niteos-Session")
        or request.cookies.get("niteos_session")
        or ""
    ).strip()
    return verify_session(secret, raw)


def _auth_context(request: web.Request, body: dict | None = None) -> dict[str, Any]:
    """Return {uid, role, share_id?} or raise HTTP error."""
    settings: Settings = request.app["runtime"].settings
    init_data = request.headers.get("X-Telegram-Init-Data") or ""
    if body and not init_data:
        init_data = str(body.get("init_data") or "")
    if init_data:
        uid = int(parse_init_data(init_data, settings.bot_token)["user_id"])
        if access_enabled(settings) and not is_allowed(settings, uid):
            raise web.HTTPForbidden(text=DENY_TEXT)
        return {"uid": uid, "role": "telegram"}

    sess = _session_from_request(request)
    if sess:
        return {
            "uid": int(sess.get("uid") or STAFF_UID),
            "role": str(sess.get("role") or "staff"),
            "share_id": sess.get("share_id"),
        }

    token = request.headers.get("X-Niteos-Token") or ""
    if body and not token:
        token = str(body.get("token") or "")
    if settings.webapp_token and token and token == settings.webapp_token:
        return {"uid": 2, "role": "staff"}

    # Localhost bypass only when no password gate configured
    if not settings.webapp_password and _client_ip(request) in {"127.0.0.1", "::1"}:
        return {"uid": 1, "role": "staff"}

    if settings.webapp_password:
        raise web.HTTPUnauthorized(text="Нужен пароль или одноразовая ссылка")
    raise web.HTTPUnauthorized(text="Открой приложение из Telegram-бота")


def _require_user(request: web.Request, body: dict | None = None) -> int:
    return int(_auth_context(request, body)["uid"])


def _require_staff(request: web.Request, body: dict | None = None) -> int:
    ctx = _auth_context(request, body)
    if ctx.get("role") not in {"staff", "telegram"}:
        raise web.HTTPForbidden(text="Только для команды Нитеос")
    return int(ctx["uid"])


async def meta(request: web.Request) -> web.Response:
    _require_user(request, None)
    geo = geo_payload()
    ctx = _auth_context(request, None)
    return web.json_response(
        {
            "okved": all_codes(),
            "cities": geo["cities"],
            "geo": geo,
            "role": ctx.get("role"),
            "auth": True,
            "spheres": [
                {
                    "id": s.id,
                    "title": s.title,
                    "idea": s.idea,
                    "okved": [
                        {"code": c, "title": title_for(c) or c}
                        for c in s.okved
                    ],
                    "options": [
                        {"id": o.id, "label": o.label, "query": o.query}
                        for o in s.options
                    ],
                }
                for s in SPHERES.values()
            ],
            "counts": [1, 5, 10, 20, 50] if ctx.get("role") != "guest" else [1, 5],
        }
    )


async def auth_status(request: web.Request) -> web.Response:
    settings: Settings = request.app["runtime"].settings
    try:
        ctx = _auth_context(request, None)
        return web.json_response(
            {
                "ok": True,
                "role": ctx.get("role"),
                "password_required": bool(settings.webapp_password),
            }
        )
    except web.HTTPUnauthorized:
        return web.json_response(
            {
                "ok": False,
                "role": None,
                "password_required": bool(settings.webapp_password),
            }
        )


async def login(request: web.Request) -> web.Response:
    settings: Settings = request.app["runtime"].settings
    try:
        body = await request.json()
    except Exception as exc:
        raise web.HTTPBadRequest(text="JSON") from exc
    password = str(body.get("password") or "")
    if not password_ok(settings, password):
        raise web.HTTPUnauthorized(text="Неверный пароль")
    token = make_staff_session(settings)
    # Return token in body too — Cloudflare/cookie quirks won't kill the session.
    resp = web.json_response({"ok": True, "role": "staff", "session": token})
    forwarded = (request.headers.get("X-Forwarded-Proto") or "").lower()
    origin = (request.headers.get("Origin") or request.headers.get("Referer") or "").lower()
    secure = (
        request.url.scheme == "https"
        or forwarded == "https"
        or origin.startswith("https://")
    )
    set_session_cookie(resp, token, secure=secure)
    return resp


async def logout(_request: web.Request) -> web.Response:
    resp = web.json_response({"ok": True})
    clear_session_cookie(resp)
    return resp


async def share_enter(request: web.Request) -> web.Response:
    runtime: HuntRuntime = request.app["runtime"]
    try:
        body = await request.json()
    except Exception as exc:
        raise web.HTTPBadRequest(text="JSON") from exc
    token = str(body.get("token") or body.get("s") or "").strip()
    if not token:
        raise web.HTTPBadRequest(text="Нет токена ссылки")
    ip = _client_ip(request)
    row = await db.consume_share_link(runtime.database, token=token, ip=ip)
    if not row:
        raise web.HTTPForbidden(
            text="Ссылка недействительна, уже использована или привязана к другому устройству"
        )
    session = make_guest_session(runtime.settings, share_id=int(row["id"]))
    resp = web.json_response(
        {
            "ok": True,
            "role": "guest",
            "session": session,
            "label": row.get("label") or "",
            "hint": "Гостевой доступ: ссылка одноразовая и привязана к этому устройству",
        }
    )
    forwarded = (request.headers.get("X-Forwarded-Proto") or "").lower()
    origin = (request.headers.get("Origin") or request.headers.get("Referer") or "").lower()
    secure = (
        request.url.scheme == "https"
        or forwarded == "https"
        or origin.startswith("https://")
    )
    set_session_cookie(resp, session, max_age=24 * 3600, secure=secure)
    return resp


async def share_create(request: web.Request) -> web.Response:
    runtime: HuntRuntime = request.app["runtime"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    _require_staff(request, body if isinstance(body, dict) else None)
    label = str((body or {}).get("label") or "клиент").strip()[:80]
    # Always one-shot for clients — no multi-use links from UI.
    max_uses = 1
    hours = int((body or {}).get("hours") or 72)
    hours = max(1, min(hours, 168))
    expires = (
        datetime.now(timezone.utc) + timedelta(hours=hours)
    ).isoformat()
    token = new_share_token()
    share_id = await db.create_share_link(
        runtime.database,
        token=token,
        label=label,
        max_uses=max_uses,
        expires_at=expires,
    )
    base = ""
    origin = (request.headers.get("Origin") or "").strip().rstrip("/")
    referer = (request.headers.get("Referer") or "").strip()
    if origin.startswith("http"):
        base = origin
    elif referer.startswith("http"):
        try:
            from urllib.parse import urlparse

            p = urlparse(referer)
            if p.scheme and p.netloc:
                base = f"{p.scheme}://{p.netloc}"
        except Exception:
            base = ""
    if not base:
        base = (runtime.webapp_url or "").rstrip("/") or str(request.url.origin())
    url = f"{base}/?s={token}"
    return web.json_response(
        {
            "ok": True,
            "id": share_id,
            "token": token,
            "url": url,
            "max_uses": 1,
            "expires_at": expires,
            "label": label,
            "hint": "Одноразовая ссылка: один человек / одно устройство. После входа ссылка сгорает.",
        }
    )


async def create_hunt(request: web.Request) -> web.Response:
    runtime: HuntRuntime = request.app["runtime"]
    try:
        body = await request.json()
    except Exception as exc:
        raise web.HTTPBadRequest(text="JSON") from exc
    ctx = _auth_context(request, body)
    user_id = int(ctx["uid"])

    phrase = str(body.get("phrase") or "").strip()
    okved_list = body.get("okved") or []
    if isinstance(okved_list, str):
        okved_raw = okved_list.strip()
    else:
        okved_raw = ", ".join(str(x).strip() for x in okved_list if str(x).strip())
    city = str(body.get("city") or "").strip()
    if city.lower() in {"вся россия", "россия", "all", "*"}:
        city = ""
    raw_cities = body.get("cities") or []
    if isinstance(raw_cities, str):
        raw_cities = [x.strip() for x in raw_cities.replace(";", ",").split(",") if x.strip()]
    else:
        raw_cities = [str(x).strip() for x in raw_cities if str(x).strip()]
    raw_regions = body.get("regions") or []
    if isinstance(raw_regions, str):
        raw_regions = [x.strip() for x in raw_regions.replace(";", ",").split(",") if x.strip()]
    else:
        raw_regions = [str(x).strip() for x in raw_regions if str(x).strip()]
    sel_cities, sel_regions, _geo_label = parse_geo_selection(
        city=city,
        cities=raw_cities,
        regions=raw_regions,
    )
    city_store = ", ".join(sel_cities)
    region_store = ", ".join(sel_regions)
    try:
        count = int(body.get("count") or 10)
    except (TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(text="count") from exc
    if ctx.get("role") == "guest":
        count = max(1, min(count, 5))
    else:
        count = max(1, min(count, 50))
    sphere_ids = [str(s) for s in (body.get("spheres") or []) if str(s)]
    search_queries = body.get("search_queries") or body.get("queries") or []
    if isinstance(search_queries, str):
        search_queries = [q.strip() for q in search_queries.split(",") if q.strip()]
    else:
        search_queries = [str(q).strip() for q in search_queries if str(q).strip()]
    if not phrase and not okved_raw and not sphere_ids and not search_queries:
        raise web.HTTPBadRequest(text="Нужен запрос, сфера или ОКВЭД")

    running = await db.running_hunt_for_user(runtime.database, user_id)
    if running:
        # Don't silently reuse a hung hunt — cancel and start fresh
        await db.finish_hunt(runtime.database, running, "error")
        log.info("cancelled previous hunt %s for user %s", running, user_id)

    hunt_id = await db.create_hunt(
        runtime.database,
        user_id,
        phrase,
        sphere_ids,
        okved_raw,
        count,
        region=region_store,
        city=city_store,
        status="queued",
    )
    await db.set_hunt_progress(runtime.database, hunt_id, "В очереди. Агенты сейчас возьмут.")
    await runtime.queue.put(
        {
            "id": hunt_id,
            "user_id": user_id,
            "phrase": phrase,
            "okved_raw": okved_raw,
            "sphere_ids": sphere_ids,
            "search_queries": search_queries,
            "count": count,
            "city": city_store,
            "cities": sel_cities,
            "regions": sel_regions,
        }
    )
    return web.json_response({"id": hunt_id, "status": "queued"})


async def hunt_status(request: web.Request) -> web.Response:
    runtime: HuntRuntime = request.app["runtime"]
    try:
        hunt_id = int(request.match_info["hunt_id"])
    except ValueError as exc:
        raise web.HTTPBadRequest(text="id") from exc
    user_id = _require_user(request, None)
    payload = await db.get_hunt(runtime.database, hunt_id)
    if not payload:
        raise web.HTTPNotFound(text="нет охоты")
    if payload["user_id"] not in {user_id, 0} and _client_ip(request) not in {"127.0.0.1", "::1"}:
        raise web.HTTPForbidden(text="чужая охота")
    return web.json_response(payload)


async def index(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEB_DIR / "index.html")


async def favicon(_request: web.Request) -> web.FileResponse:
    path = WEB_DIR / "favicon.ico"
    if not path.exists():
        path = WEB_DIR / "favicon.png"
    return web.FileResponse(path)


async def favicon_png(_request: web.Request) -> web.FileResponse:
    path = WEB_DIR / "favicon.png"
    if not path.exists():
        path = WEB_DIR / "favicon.ico"
    return web.FileResponse(path)


async def worker(runtime: HuntRuntime) -> None:
    while True:
        job = await runtime.queue.get()
        hunt_id = int(job["id"])
        log.info("hunt worker start %s", hunt_id)
        database = await connect(runtime.settings)

        async def progress(text: str) -> None:
            log.info("hunt %s %s", hunt_id, text.replace("\n", " / "))

        try:
            await run_hunt(
                settings=runtime.settings,
                database=database,
                user_id=int(job["user_id"]),
                sphere_ids=list(job["sphere_ids"]),
                phrase=str(job["phrase"]),
                okved_raw=str(job["okved_raw"]),
                search_queries=list(job.get("search_queries") or []),
                target_count=int(job["count"]),
                region=", ".join(job.get("regions") or []),
                city=str(job.get("city") or ""),
                cities=list(job.get("cities") or []),
                regions=list(job.get("regions") or []),
                progress=progress,
                hunt_id=hunt_id,
            )
        except Exception:
            log.exception("hunt worker failed %s", hunt_id)
            try:
                await db.finish_hunt(database, hunt_id, "error")
            except Exception:
                log.exception("cannot mark hunt error")
        finally:
            await database.close()
            runtime.queue.task_done()


async def mark_company_kp_api(request: web.Request) -> web.Response:
    runtime: HuntRuntime = request.app["runtime"]
    try:
        body = await request.json()
    except Exception as exc:
        raise web.HTTPBadRequest(text="JSON") from exc
    _auth_context(request, body)
    inn = str(body.get("inn") or "").strip()
    if not inn:
        raise web.HTTPBadRequest(text="inn")
    ok = await db.mark_company_kp(runtime.database, inn)
    if not ok:
        raise web.HTTPNotFound(text="компания не найдена")
    return web.json_response({"ok": True, "inn": inn, "kp_status": "в КП"})


async def list_kp_api(request: web.Request) -> web.Response:
    runtime: HuntRuntime = request.app["runtime"]
    _auth_context(request, {})
    items = await db.list_kp_companies(runtime.database, limit=80)
    return web.json_response({"ok": True, "items": items, "count": len(items)})


def build_app(runtime: HuntRuntime) -> web.Application:
    app = web.Application()
    app["runtime"] = runtime
    app.router.add_get("/", index)
    app.router.add_get("/favicon.ico", favicon)
    app.router.add_get("/favicon.png", favicon_png)
    app.router.add_get("/apple-touch-icon.png", favicon_png)
    app.router.add_get("/apple-touch-icon", favicon_png)
    app.router.add_get("/api/auth", auth_status)
    app.router.add_post("/api/login", login)
    app.router.add_post("/api/logout", logout)
    app.router.add_post("/api/share/enter", share_enter)
    app.router.add_post("/api/share/create", share_create)
    app.router.add_get("/api/meta", meta)
    app.router.add_post("/api/hunt", create_hunt)
    app.router.add_get("/api/hunt/{hunt_id}", hunt_status)
    app.router.add_post("/api/company/kp", mark_company_kp_api)
    app.router.add_get("/api/kp", list_kp_api)
    app.router.add_static("/static", WEB_DIR, show_index=False)
    app.router.add_static("/assets", WEB_DIR / "assets", show_index=False)
    # Keep legacy HTML available during rollout
    app.router.add_get("/legacy", lambda _r: web.FileResponse(WEB_DIR / "index.legacy.html"))
    return app


async def start_http(runtime: HuntRuntime) -> web.AppRunner:
    app = build_app(runtime)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", runtime.settings.webapp_port)
    await site.start()
    log.info("webapp http://127.0.0.1:%s", runtime.settings.webapp_port)
    return runner
