# BoostX — Uptime Overlay (Render Free + UptimeRobot)

Этот пакет добавляет **встроенный health-сервер** на `aiohttp`, чтобы Render видел открытый порт,
а UptimeRobot мог пинговать сервис и не давать ему «засыпать».

## Что входит
- `health_server.py` — мини HTTP-сервер:
  - `GET /` и `/health` → `200 OK`
  - `GET /status` → JSON со статусом
- `render.yaml` — запускает сразу три процесса:
  1) `python health_server.py` (порт `$PORT` или 10000)
  2) `python sync_gist.py` (если он есть в корне, для Gist-баланса)
  3) `python shop_bot.py` (сам бот)

> Если у тебя нет `sync_gist.py`, просто оставь файл `render.yaml` — он всё равно запустит health-сервер и бота.

## Требования
В `requirements.txt` должны быть как минимум:
```
python-telegram-bot==21.6
aiohttp
requests
python-dotenv
```

## Настройка UptimeRobot
1. URL для мониторинга: `https://<твой-сервис>.onrender.com/health` (или `/`)
2. Тип: **HTTP(s)**
3. Интервал: **5 minutes**

## Развёртывание
1. Скопируй файлы в корень проекта (рядом с `shop_bot.py`).
2. Закоммить и запушь.
3. Render подхватит `render.yaml` и поднимет порт.

В логах увидишь примерно так:
```
🌐 Health server starting on 0.0.0.0:10000
🧩 Gist sync starting…
🚀 Bot is running...
✅ Webhook удалён, polling активирован.
```
