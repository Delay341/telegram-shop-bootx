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

# Register support reply early
register_reply_handler(bot)
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



# --- Promo management (admin) ---
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PROMO_FILE = os.getenv("PROMO_FILE", os.path.join(os.path.dirname(__file__), "promos.json"))

def _load_promos():
    try:
        import json
from handlers.reply import register_reply_handler
        if os.path.exists(PROMO_FILE):
            return json.loads(open(PROMO_FILE,'r',encoding='utf-8').read() or '{}')
    except Exception:
        pass
    return {}

def _save_promos(d):
    try:
        import json
        open(PROMO_FILE,'w',encoding='utf-8').write(json.dumps(d, ensure_ascii=False, indent=2))
    except Exception:
        pass

@bot.message_handler(commands=['promo_list'])
def promo_list(m):
    if m.from_user.id != ADMIN_ID:
        return
    d = _load_promos()
    if not d:
        bot.reply_to(m, "Промокодов нет.")
        return
    lines = [f"{k}: x{v}" for k,v in d.items()]
    bot.reply_to(m, "\n".join(lines))

@bot.message_handler(commands=['promo_add'])
def promo_add(m):
    if m.from_user.id != ADMIN_ID:
        return
    # /promo_add CODE 0.85
    parts = (m.text or '').split()
    if len(parts) != 3:
        bot.reply_to(m, "Формат: /promo_add CODE 0.85")
        return
    code, factor = parts[1].upper(), parts[2]
    try:
        f = float(factor)
        d = _load_promos()
        d[code] = f
        _save_promos(d)
        bot.reply_to(m, f"✅ Добавлен {code}: x{f}")
    except Exception:
        bot.reply_to(m, "Не удалось добавить промокод. Пример: /promo_add VIP20 0.80")

@bot.message_handler(commands=['promo_del'])
def promo_del(m):
    if m.from_user.id != ADMIN_ID:
        return
    parts = (m.text or '').split()
    if len(parts) != 2:
        bot.reply_to(m, "Формат: /promo_del CODE")
        return
    code = parts[1].upper()
    d = _load_promos()
    if code in d:
        del d[code]
        _save_promos(d)
        bot.reply_to(m, f"🗑 Удалён {code}")
    else:
        bot.reply_to(m, "Такого кода нет.")