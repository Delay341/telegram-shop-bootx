import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import telebot
from telebot.apihelper import ApiTelegramException
from handlers.menu import register_handlers


# --- Мини HTTP-сервер для Render ---
class _Health(BaseHTTPRequestHandler):
PORT = int(os.environ.get("PORT", "10000"))
threading.Thread(target=lambda: HTTPServer(("", PORT), _Health).serve_forever(), daemon=True).start()

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


def _run_health_server():
    port = int(os.getenv("PORT", "10000"))  # Render передает PORT
    httpd = HTTPServer(("0.0.0.0", port), _Health)
    httpd.serve_forever()


# Запускаем HTTP-сервер в отдельном потоке
threading.Thread(target=_run_health_server, daemon=True).start()
# -----------------------------------


# --- Telegram Bot ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN не задан.")
    raise SystemExit

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
register_handlers(bot)

# --- Диагностические логи ---
me = bot.get_me()
print(f"✅ getMe: @{me.username} (id={me.id})")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", TOKEN)
print(f"🔑 token tail: ...{TOKEN[-6:]}")

# 🧹 Сброс вебхука, чтобы избежать 409 ошибок
try:
    bot.remove_webhook(drop_pending_updates=True)
except Exception:
    pass
time.sleep(1)

print("✅ Бот запущен и готов к работе...")

def run_polling_with_retry():
    attempts = 0
    while True:
        try:
            print("▶️  Starting polling...")
            bot.infinity_polling(skip_pending=True, allowed_updates=[])
        except ApiTelegramException as e:
            if '409' in str(e):
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

run_polling_with_retry()


# --- Support bridge & /reply ---
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
USER_ASK_STATE = set()

@bot.message_handler(commands=["support"])
def support_cmd(m):
    USER_ASK_STATE.add(m.from_user.id)
    bot.send_message(m.chat.id, "✏️ Напишите ваш вопрос — я передам его в поддержку.")

@bot.message_handler(commands=["reply"])
def reply_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return
    try:
        _, uid_str, *rest = m.text.split()
        uid = int(uid_str)
        text = " ".join(rest).strip()
        if not text:
            raise ValueError
    except Exception:
        bot.reply_to(m, "Формат: /reply <user_id> <текст>")
        return
    try:
        bot.send_message(uid, text, parse_mode="HTML")
        bot.reply_to(m, f"✅ Отправлено пользователю {uid}")
    except Exception as e:
        bot.reply_to(m, f"⚠️ Не удалось отправить: {e}")

@bot.message_handler(func=lambda msg: msg.from_user.id in USER_ASK_STATE, content_types=["text", "photo", "document"])
def support_forward(m):
    USER_ASK_STATE.discard(m.from_user.id)
    text = m.text or m.caption or "(без текста)"
    info = f"📩 <b>Новый вопрос</b>\nОт: @{m.from_user.username or '—'} (id {m.from_user.id})\n\n<b>Текст:</b>\n{text}\n\nОтветьте командой:\n/reply {m.from_user.id} ваш_текст"
    if ADMIN_ID:
        try:
            if m.photo:
                file_id = m.photo[-1].file_id
                bot.send_photo(ADMIN_ID, file_id, caption=info, parse_mode="HTML")
            elif m.document:
                bot.send_document(ADMIN_ID, m.document.file_id, caption=info, parse_mode="HTML")
            else:
                bot.send_message(ADMIN_ID, info, parse_mode="HTML")
        except Exception:
            pass
    bot.reply_to(m, "✅ Ваше сообщение передано в поддержку. Ответ придёт сюда.")
