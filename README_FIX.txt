Что исправлено:
- Вернули иконки: assets/boostx.png, telegram.png, youtube.png, tiktok.png
- Кнопка «💰 Баланс» показывает баланс и выдаёт «💸 Пополнить»
- Вариант A пополнения: /pay, /paid (подтверждение админом), /topup <сумма> (уникальная сумма + код)
- Восстановлены категории и товары (config/config.json). Можно править цены и provider_service IDs.
- Устойчивый polling c ретраями и health-сервер для Render.

Переменные окружения:
TELEGRAM_BOT_TOKEN=...
ADMIN_ID=...
ADMIN_LOG_CHAT_ID=
CARD_DETAILS=ссылка на оплату
PAY_INSTRUCTIONS=текст инструкции
SUPPLIER_API_URL=https://looksmm.ru/api/v2
SUPPLIER_API_KEY=ваш_ключ
PRICING_MULTIPLIER=2.0
DB_PATH=data/db.sqlite
