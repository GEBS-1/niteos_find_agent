"""Targeted Kazan Arena enrich on VPS."""
from __future__ import annotations

from sshutil import ROOT, load_env, run, ssh_connect

REMOTE = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import asyncio, json
from pathlib import Path
import httpx
from dotenv import load_dotenv
load_dotenv('/opt/niteos/.env')

from app.config import load_settings
from app.contacts import enrich_contacts
from app.dadata import DaData
from app.enrich import enrich_from_dadata
from app.llm import RouterAI
from app.objects import collect_object_photos, object_company_relation, search_objects
from app.owners import resolve_building_owners

OUT = Path('/tmp/niteos_arena_card.json')

def pick_obj(objs):
    scored = []
    for o in objs or []:
        t = (o.get('title') or '').lower().replace('ё','е')
        maps = str(o.get('maps_yandex') or '')
        score = 0
        if 'ак барс' in t or 'ak bars' in t: score += 50
        if 'казань арена' in t or 'kazan arena' in t: score += 45
        if 'арена' in t: score += 20
        if 'стадион' in t: score += 15
        if '/org/' in maps: score += 25
        if 'text=' in maps or 'pt=' in maps: score -= 10
        if 'аквапарк' in t or 'ривьера' in t or 'жк' in t: score -= 40
        scored.append((score, o))
    scored.sort(key=lambda x: -x[0])
    return scored[0][1] if scored and scored[0][0] > 0 else (objs[0] if objs else None)

async def main():
    settings = load_settings()
    llm = RouterAI(settings.router_api_key, base_url=settings.router_base_url, model=settings.router_model, timeout=90)
    dadata = DaData(settings.dadata_api_key)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
        'Accept-Language': 'ru-RU,ru;q=0.9',
    }
    async with httpx.AsyncClient(timeout=40.0, follow_redirects=True, headers=headers) as client:
        objs = []
        for q in ['Ак Барс Арена', 'Казань Арена', 'стадион Казань Арена']:
            part = await search_objects(client, query=q, cities=['Казань'], limit=8)
            objs.extend(part or [])
            print('query', q, 'hits', len(part or []), flush=True)
        obj = pick_obj(objs)
        if not obj:
            # hard pin known org card
            obj = {
                'title': 'Ак Барс Арена',
                'address': 'Казань, проспект Хусаина Ямашева, 115А',
                'city': 'Казань',
                'maps_yandex': 'https://yandex.com/maps/org/ak_bars_arena/1216041023',
            }
        obj = {**obj, 'city': 'Казань'}
        # Prefer known org URL if title matches arena
        t = (obj.get('title') or '').lower().replace('ё','е')
        if ('арена' in t or 'стадион' in t) and '/org/' not in str(obj.get('maps_yandex') or ''):
            obj['maps_yandex'] = 'https://yandex.com/maps/org/ak_bars_arena/1216041023'
        print('OBJ', obj.get('title'), '|', obj.get('address'), '|', (obj.get('maps_yandex') or '')[:90], flush=True)

        photos, photo_notes = await collect_object_photos(client, obj)
        print('photos', len(photos), photo_notes, flush=True)
        for u in photos[:5]:
            print(' PHOTO', u[:130], flush=True)

        cands = await resolve_building_owners(http=client, dadata=dadata, obj=obj, city='Казань', llm=llm)
        print('cands', len(cands), flush=True)
        party = None
        rel = None
        for cand in cands:
            if not cand.get('suggest'):
                continue
            p = enrich_from_dadata(cand['suggest'])
            if not p:
                continue
            r = object_company_relation(p, obj)
            print(' cand', cand.get('source'), p.get('inn'), (p.get('name') or '')[:55], 'rel', r.get('confidence'), flush=True)
            if (p.get('inn') == '1655252924') or (not party) or int(r.get('confidence') or 0) > int((rel or {}).get('confidence') or 0):
                party, rel = p, r
                if p.get('inn') == '1655252924':
                    break
        if not party or party.get('inn') != '1655252924':
            sug = await dadata.find_by_inn('1655252924')
            if sug:
                party = enrich_from_dadata(sug)
                rel = object_company_relation(party, obj)
                print('forced inn 1655252924', flush=True)

        party['object'] = {
            'title': obj.get('title') or '',
            'address': obj.get('address') or '',
            'source': obj.get('source') or '',
            'maps_yandex': obj.get('maps_yandex') or '',
            'maps_google': obj.get('maps_google') or '',
            'url_2gis': obj.get('url_2gis') or '',
            'relation': rel or {},
            'photo_notes': photo_notes,
            'verified': True,
        }
        party['photos'] = photos
        party['requested_city'] = 'Казань'
        party['object_address'] = obj.get('address') or ''

        enriched = await enrich_contacts(party, client=client, llm=llm)
        enriched['photos'] = photos or enriched.get('photos') or []
        enriched['object'] = {**(party.get('object') or {}), **(enriched.get('object') or {})}
        p = enriched.get('presence') or {}
        summary = {
            'building': (enriched.get('object') or {}).get('title'),
            'address': (enriched.get('object') or {}).get('address'),
            'maps': (enriched.get('object') or {}).get('maps_yandex'),
            'company': enriched.get('name'),
            'inn': enriched.get('inn'),
            'director': enriched.get('management_label') or enriched.get('management'),
            'founders': (enriched.get('founders') or [])[:5],
            'phone': (p.get('phone') or {}).get('value'),
            'site': (p.get('site') or {}).get('value'),
            'vk': (p.get('vk_company') or {}).get('value'),
            'vk_lpr': (p.get('vk_lpr') or {}).get('value'),
            'telegram': (p.get('telegram') or {}).get('value'),
            'whatsapp': (p.get('whatsapp') or {}).get('value'),
            'photos': (enriched.get('photos') or [])[:6],
            'photo_notes': (enriched.get('object') or {}).get('photo_notes'),
            'relation': (enriched.get('object') or {}).get('relation'),
            'checks': (p.get('checks') or [])[:25],
        }
        OUT.write_text(json.dumps({'summary': summary, 'card': enriched}, ensure_ascii=False, indent=2), encoding='utf-8')
        print('SUMMARY', json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    await llm.aclose(); await dadata.aclose()

asyncio.run(main())
PY
"""


def main() -> None:
    client = ssh_connect(load_env())
    sftp = client.open_sftp()
    sftp.put(str(ROOT / "app/objects.py"), "/opt/niteos/app/objects.py")
    sftp.put(str(ROOT / "app/share_auth.py"), "/opt/niteos/app/share_auth.py")
    sftp.put(str(ROOT / "app/webapp.py"), "/opt/niteos/app/webapp.py")
    sftp.put(str(ROOT / "web/index.html"), "/opt/niteos/web/index.html")
    sftp.close()
    run(
        client,
        "systemctl kill -s SIGKILL niteos-bot || true; sleep 1; "
        "systemctl reset-failed niteos-bot || true; systemctl start niteos-bot; sleep 4; "
        "systemctl is-active niteos-bot",
        timeout=40,
    )
    code, text = run(client, REMOTE, timeout=420)
    print((text or "")[-14000:])
    print("exit", code)
    _, raw = run(client, "cat /tmp/niteos_arena_card.json", timeout=30)
    out = ROOT / "data" / "arena_hunt_live.json"
    out.write_text(raw or "{}", encoding="utf-8")
    print("saved", out, "bytes", len(raw or ""))
    client.close()


if __name__ == "__main__":
    main()
