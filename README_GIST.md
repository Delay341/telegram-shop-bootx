
# BoostX — Gist Balance Sync (Render Free)

Этот пакет добавляет синхронизацию `balances.json` c **GitHub Gist**, чтобы баланс пользователей НЕ терялся на бесплатном Render.

## Что входит
- `sync_gist.py` — фоновой процесс, который:
  - при старте тянет `balances.json` из Gist (если он есть);
  - каждые 20 секунд пушит локальные изменения в Gist;
  - подтягивает изменения из Gist (если ты отредактируешь файл вручную).
- `render.yaml` — запускает `sync_gist.py` в фоне и затем `shop_bot.py`.

## Настройка окружения (Render → Environment)
Обязательно добавь:
- `BOT_TOKEN` — токен бота
- `ADMIN_ID` — твой Telegram user ID (число)
- `LOOKSMM_KEY` — API ключ
- `GIST_ID` — ID твоего secret gist (например `297a8c8b5700f46fc4c42da240840d12`)
- `GITHUB_TOKEN` — персональный токен GitHub с правом **gist**
- `BALANCES_FILE` — `balances.json` (по умолчанию)
- (опционально) `GIST_SYNC_INTERVAL` — период синка в секундах (по умолчанию 20)

## Как использовать
1. Разархивируй файлы в корень проекта (рядом с `shop_bot.py`).
2. Закоммить и запушь.
3. На Render нажми **Deploy**.

В логах увидишь:
```
🧩 Gist sync starting…
⬆️  Pushed balances.json to Gist. / ⬇️ Pulled balances.json from Gist.
🚀 Bot is running...
```
