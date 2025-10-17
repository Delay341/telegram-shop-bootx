
import os
from telebot import TeleBot, apihelper

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

def _chunk(text: str, n: int = 4096):
    for i in range(0, len(text), n):
        yield text[i:i+n]

def register_reply_handler(bot: TeleBot):
    @bot.message_handler(commands=['reply', 'replay'])
    def handle_reply(message):
        # Only admin
        if message.from_user.id != ADMIN_ID:
            return

        # Expect: /reply <user_id> <text>
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 3:
            bot.reply_to(
                message,
                "❗ Формат: /reply <user_id> <текст>\n"
                "Пример: /reply 5623297755 Спасибо за обращение!"
            )
            return

        # Parse user id
        try:
            target_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❗ user_id должен быть числом. Пример: /reply 5623297755 текст")
            return

        text = parts[2].strip()
        if not text:
            bot.reply_to(message, "❗ Пустой текст ответа.")
            return

        try:
            header = "📩 Ответ от поддержки:\n\n"
            for chunk in _chunk(header + text):
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
