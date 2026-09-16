# NITEOS Hunt V5

Основной путь — **бесплатный** (как в классическом Niteos):

1. Объекты: Яндекс Maps `/org` + 2ГИС HTML + Nominatim  
2. Фото/координаты: карточка Яндекса / Яндекс.Картинки / OSM  
3. Юрлицо: DaData + List-Org + открытый web  
4. Кадастр: НСПД soft (или HTTP, если задан `CADASTRE_API_URL`)  

`NO_SOURCE = NO_FACT`. Платные Maps API-ключи **не обязательны**.  
Фикстуры/смоки под конкретные заводы и 2GIS API — в `_archive/`.

## Запуск

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/bootstrap_env.py   # тянет ключи из ../.env (DaData и т.п.)
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Открыть `http://127.0.0.1:8001`.

## API

- `GET /api/providers`
- `GET /api/system-design`
- `POST /api/hunts` — `{ "city", "query", "count" }`
- `GET /api/hunts/{id}`
- `GET /api/hunts/{id}/results`
- `POST /api/objects/{id}/proposal` — только при `LLM_ENABLED=1`

## Тесты

```bash
pytest -q
```
