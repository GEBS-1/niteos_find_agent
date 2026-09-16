# Provider matrix

| Задача | Primary | Fallback | LLM? |
|---|---|---|---|
| Найти здания | 2GIS Places | Nominatim/OSM | Нет |
| Проверить видимость с дороги | Yandex Panorama | публичное фото | Vision только для оценки |
| Фото фасада | public visual source | panorama screenshot/manual source | Vision для score |
| Кадастр | configured cadastral/EGRN provider | manual review | Нет |
| Юрлицо по ИНН | DaData | Контур/СПАРК adapter | Нет |
| Владельцы | registry provider + recursion | manual review | Нет |
| ЛПР | официальный сайт + web search | отраслевые источники | Может помочь классифицировать |
| Телефон/e-mail человека | public search + documents | professional profile | Нет для извлечения; LLM только cross-check |
| OCR PDF/сканов | Yandex Vision OCR | local OCR | Нет |
| Анализ фасада | OpenAI Terra vision | Yandex multimodal model if configured | Да |
| КП | OpenAI Terra | YandexGPT | Да |
