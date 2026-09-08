# NITEOS Hunt UI

Интерфейс на дизайне [hunt-hub-interface](https://github.com/GEBS-1/hunt-hub-interface): React + Vite + Tailwind.

Подключён к существующим API Нитеос (`/api/login`, `/api/meta`, `/api/hunt`, `/api/kp`, `/api/share/*`) без изменения логики охоты/результатов.

```bash
cd frontend
npm install
npm run build   # → ../web
npm run dev     # proxy на :8088
```

Старый UI: `/legacy` или `web/index.legacy.html`.
