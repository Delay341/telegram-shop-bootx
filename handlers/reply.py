# handlers/reply.py
import os
import re
from telebot import TeleBot, apihelper

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

def _chunk(text: str, n: int = 4096):
    for i in range(0, len(text), n):
        yield text[i:i+n]

def _is_admin(user_id: int) -> bool:
    return ADMIN_ID and (user_id == ADMIN_ID)

def register_reply_handler(bot: TeleBot):
    @bot.message_handler(commands=['whoami'])
    def whoami(message):
        bot.reply_to(message, f"👤 Ваш Telegram ID: {message.from_user.id}\n"
                              f"🔐 ADMIN_ID в окружении: {ADMIN_ID or 'не задан'}")

    @bot.message_handler(func=lambda m: isinstance(m.text, str) and
                          re.match(r'^/(reply|replay)(@\w+)?\b', m.text.strip(), flags=re.IGNORECASE))
    def reply_handler(message):
        text_raw = (message.text or "").strip()
        # print log (Render logs)
        try:
            print(f"[reply] from={message.from_user.id} text={text_raw!r}")
        except Exception:
            pass

        if not _is_admin(message.from_user.id):
            bot.reply_to(message, "❗ Команда доступна только администратору.")
            return

        head_removed = re.sub(r'^/(reply|replay)(@\w+)?\s*', '', text_raw, count=1, flags=re.IGNORECASE).strip()
        if not head_removed:
            bot.reply_to(message, "❗ Формат: /reply <user_id> <текст>\nПример: /reply 5623297755 Спасибо!")
            return

        parts = head_removed.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "❗ Формат: /reply <user_id> <текст>\nПример: /reply 5623297755 Спасибо!")
            return

        try:
            target_id = int(parts[0])
        except ValueError:
            bot.reply_to(message, "❗ user_id должен быть числом. Пример: /reply 5623297755 Спасибо!")
            return

        body = parts[1].strip()
        if not body:
            bot.reply_to(message, "❗ Пустой текст ответа.")
            return

        try:
            header = "📩 Ответ от поддержки:\n\n"
            for chunk in _chunk(header + body):
                bot.send_message(target_id, chunk)
            bot.reply_to(message, "✅ Отправлено.")
        except apihelper.ApiTelegramException as e:
            desc = ""
            try:
                desc = e.result_json.get("description", "")
            except Exception:
                desc = str(e)
            bot.reply_to(
                message,
                "⚠️ Не удалось отправить сообщение пользователю.\n"
                f"Причина: {desc}\n"
                "Проверь, что пользователь писал боту и не блокировал его."
            )
