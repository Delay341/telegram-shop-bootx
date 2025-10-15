import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import telebot
from handlers.menu import register_handlers


# --- Мини HTTP-сервер для Render ---
class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"BoostX bot OK")


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

# 🧹 Сброс вебхука, чтобы избежать 409 ошибок
bot.remove_webhook()
time.sleep(1)

print("✅ Бот запущен и готов к работе...")
bot.infinity_polling(skip_pending=True)
