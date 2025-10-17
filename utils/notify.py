
import os
from telebot import TeleBot
LOG_CHAT_ID = int(os.getenv("ADMIN_LOG_CHAT_ID", os.getenv("ADMIN_ID","0") or 0))
def safe_send(bot: TeleBot, chat_id: int, text: str):
    try:
        if chat_id: bot.send_message(chat_id, text)
    except Exception: pass
def log_admin(bot: TeleBot, text: str):
    safe_send(bot, LOG_CHAT_ID, text)
