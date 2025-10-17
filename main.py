import os, threading, time, json
from http.server import BaseHTTPRequestHandler, HTTPServer
import telebot
from telebot.apihelper import ApiTelegramException

from handlers.menu import register_handlers
from handlers.reply import register_reply_handler
from handlers.promo import register_promos
from handlers.payments import register_payments
from handlers.balance import register_balance
from handlers.orders import register_orders
from utils.db import init_db

# Health server (GET/HEAD) to avoid 501
class _Health(BaseHTTPRequestHandler):
    def _ok(self): self.send_response(200); self.end_headers(); 
    def do_GET(self): self._ok()
    def do_HEAD(self): self._ok()

PORT = int(os.environ.get("PORT","10000"))
threading.Thread(target=lambda: HTTPServer(("",PORT), _Health).serve_forever(), daemon=True).start()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN","")
if not TOKEN: print("❌ TELEGRAM_BOT_TOKEN не задан."); raise SystemExit

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# Load config
try:
    CONFIG = json.loads(open("config/config.json","r",encoding="utf-8").read())
except Exception:
    CONFIG = {"categories":[]}
bot.CONFIG = CONFIG
bot.PAYMENT_LINK = os.getenv("CARD_DETAILS","")
bot.PAY_HINT = os.getenv("PAY_INSTRUCTIONS","")

# Register handlers
init_db()
register_reply_handler(bot)
register_promos(bot)
register_payments(bot)
register_balance(bot)
register_orders(bot, bot.CONFIG)
register_handlers(bot)  # menu last

# Diagnostics
try:
    me = bot.get_me(); print(f"✅ getMe: @{me.username} (id={me.id})")
except Exception as e:
    print(f"getMe error: {e}")
print(f"🔑 token tail: ...{TOKEN[-6:]}")

try: bot.remove_webhook(drop_pending_updates=True)
except Exception: pass

time.sleep(1)

def run_polling_with_retry():
    attempts=0
    while True:
        try:
            print("▶️  Starting polling...")
            bot.infinity_polling(skip_pending=True, allowed_updates=[])
        except ApiTelegramException as e:
            msg=str(e)
            if "409" in msg or "Conflict" in msg:
                attempts+=1; wait=min(30, 5*attempts)
                print(f"⚠️  409 Conflict, retry через {wait}s (attempt {attempts})"); time.sleep(wait); continue
            print(f"⚠️  Telegram API error: {e}. Retry через 5s"); time.sleep(5)
        except Exception as e:
            print(f"⚠️  Ошибка polling: {e}. Retry через 5s"); time.sleep(5)

print("✅ Бот запущен и готов к работе...")
run_polling_with_retry()
