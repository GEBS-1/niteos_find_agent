# Старый Niteos: география (город / регион) — куда смотреть

## UI
- `frontend/src/App.tsx` — блок «География»: города, регионы, «Вся Россия», ФО
- отправка в охоту: `cities[]`, `regions[]`

## API
- `app/webapp.py` — `GET /api/meta` (дерево geo), `POST` охоты парсит `cities`/`regions`
- строки ~299–369: разбор body → `parse_geo_selection` → job

## Логика geo
- `app/geo_tree.py` — дерево ФО→регион→города, `parse_geo_selection`, `dadata_locations_multi`, `address_matches_geo`, `geo_payload`
- `app/geo.py` — `dadata_locations` (один город/регион)

## Охота / здания
- `app/agents.py` — `run_hunt(..., cities=, regions=)` → `sel_cities` / `sel_regions`
- `app/objects.py` — `search_objects(..., cities=)` — поиск по каждому городу (Яндекс→OSM→2ГИС)
- `app/owners.py` — `resolve_building_owners` — ИНН по зданию (DaData/List-Org/web)

## Запуск UI (локально)
```powershell
cd D:\Prepromo\Niteos
.\.venv\Scripts\python -m app
# http://127.0.0.1:8088
```
Пароль: `WEBAPP_PASSWORD` из корневого `.env`.
