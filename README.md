# Нитеос — охота в Telegram

Бот ищет компании по сфере / ОКВЭД / фразе, сразу пишет в SQLite, уже найденные ИНН не берёт. Агент 1 ищет, агент 2 проверяет выписку через DaData.

## Что нужно

1. Токен бота у [@BotFather](https://t.me/BotFather)
2. Ключ DaData (подсказки по организациям): https://dadata.ru/api/suggest/party/

В корне:

```
copy .env.example .env
```

Впиши `BOT_TOKEN` и `DADATA_API_KEY`. Географию выбирают в боте: вся Россия, регион или город.

## Локально

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

## Сервер

На VPS: Docker + Docker Compose. Секреты только в `.env` на сервере, не в git и не в чат.

На сервере:

```
mkdir -p /opt/niteos/data
# скопируй проект в /opt/niteos
cd /opt/niteos
nano .env
docker compose up -d --build
docker compose logs -f bot
```

В `.env` на сервере:

```
BOT_TOKEN=
DADATA_API_KEY=
```

Без `DADATA_API_KEY` бот живой, но «Начать поиск» не ищет. База компаний — `/opt/niteos/data/niteos.db`.

