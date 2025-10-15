import os, telebot
from handlers.menu import register_handlers
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN","")
if not TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN не задан."); input("Нажмите Enter, чтобы закрыть..."); raise SystemExit
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
register_handlers(bot)
bot.infinity_polling(skip_pending=True)
