
BoostX — Render Patch
=====================
Содержимое:
  • main.py — health GET/HEAD + retry 409 + безопасный polling
  • handlers/menu.py — кнопка «💰 Баланс» и обработчик
  • requirements.txt — фиксированные версии

Применение:
1) Распаковать в корень проекта с заменой файлов.
2) Render:
   Build Command:  pip install -r requirements.txt
   Start Command:  python main.py
3) Переменные окружения:
   TELEGRAM_BOT_TOKEN, ADMIN_ID, (опц. ADMIN_LOG_CHAT_ID), CARD_DETAILS, PAY_INSTRUCTIONS,
   SUPPLIER_API_URL, SUPPLIER_API_KEY, PRICING_MULTIPLIER, DB_PATH
