import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import telebot
from telebot.apihelper import ApiTelegramException

from handlers.menu import register_handlers


# --- Mini HTTP server (GET + HEAD) ---
class _Health(BaseHTTPRequestHandler):
    def _ok(self):
        self.send_response(200)
        self.end_headers()
        try:
            self.wfile.write(b"BoostX bot OK")
        except Exception:
            pass

    def do_GET(self):
        self._ok()

    def do_HEAD(self):
        self._ok()


# --- Run health server in background thread on $PORT (Render) ---
PORT = int(os.environ.get("PORT", "10000"))
threading.Thread(
    target=lambda: HTTPServer(("", PORT), _Health).serve_forever(),
    daemon=True
).start()


# --- Telegram bot init ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN не задан.")
    raise SystemExit

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
register_handlers(bot)

# --- Diagnostics ---
me = bot.get_me()
print(f"✅ getMe: @{me.username} (id={me.id})")
print(f"🔑 token tail: ...{TOKEN[-6:]}")

# --- Clean webhook & pending updates before polling ---
try:
    bot.remove_webhook(drop_pending_updates=True)
except Exception:
    pass
time.sleep(1)

# --- Safe polling with retries (handles 409 conflicts) ---
def run_polling_with_retry():
    attempts = 0
    while True:
        try:
            print("▶️  Starting polling...")
            bot.infinity_polling(skip_pending=True, allowed_updates=[])
        except ApiTelegramException as e:
            msg = str(e)
            if "409" in msg or "Conflict" in msg:
                attempts += 1
                wait = min(30, 5 * attempts)
                print(f"⚠️  409 Conflict: другой getUpdates активен. Retry через {wait}s (attempt {attempts})")
                time.sleep(wait)
                continue
            else:
                print(f"⚠️  Telegram API error: {e}. Retry через 5s")
                time.sleep(5)
                continue
        except Exception as e:
            print(f"⚠️  Ошибка polling: {e}. Retry через 5s")
            time.sleep(5)
            continue

print("✅ Бот запущен и готов к работе...")
run_polling_with_retry()


# --- Admin utilities ---
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ORDERS_FILE = os.getenv("ORDERS_FILE", os.path.join(os.path.dirname(__file__), "orders.json"))
USERS_FILE = os.getenv("USERS_FILE", os.path.join(os.path.dirname(__file__), "users.json"))

@bot.message_handler(commands=["orders"])
def orders_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return
    import json, time
    args = (m.text or "").split()
    limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
    if not os.path.exists(ORDERS_FILE):
        bot.reply_to(m, "Заказов пока нет.")
        return
    orders = json.loads(open(ORDERS_FILE,'r',encoding='utf-8').read() or '[]')[-limit:]
    if not orders:
        bot.reply_to(m, "Заказов пока нет.")
        return
    lines = []
    for o in reversed(orders):
        t = time.strftime("%Y-%m-%d %H:%M", time.localtime(o.get("ts",0)))
        lines.append(f"#{o.get('item_id')} — {o.get('qty')} шт. — {o.get('total')} ₽ — @{o.get('username') or '-'} — {t}")
    bot.reply_to(m, "\n".join(lines))

@bot.message_handler(commands=["broadcast"])
def broadcast_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return
    text = m.text.partition(" ")[2].strip()
    if not text:
        bot.reply_to(m, "Формат: /broadcast Текст рассылки")
        return
    users = []
    try:
        if os.path.exists(USERS_FILE):
            import json as _json
            users = _json.loads(open(USERS_FILE,'r',encoding='utf-8').read() or '[]')
    except Exception:
        pass
    sent = 0
    for uid in users:
        try:
            bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
            time.sleep(0.05)
        except Exception:
            pass
    bot.reply_to(m, f"✅ Отправлено: {sent}")
