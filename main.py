import os, time
from telebot import TeleBot
from handlers.balance import register_balance
from handlers.admin_exports import register_admin_exports
from handlers.autodebit import register_autodebit

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = TeleBot(TOKEN)

register_balance(bot)
register_admin_exports(bot)
register_autodebit(bot)

print("BoostX bot is starting...")
bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
