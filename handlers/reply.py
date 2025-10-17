# handlers/reply.py
import os, re
from telebot import TeleBot, apihelper

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

def _chunk(s, n=4096):
    for i in range(0, len(s), n):
        yield s[i:i+n]

def _is_admin(uid: int) -> bool:
    return ADMIN_ID and uid == ADMIN_ID

def register_reply_handler(bot: TeleBot):
    @bot.message_handler(commands=['whoami'])
    def whoami(m):
        bot.reply_to(m, f"👤 ID: {m.from_user.id}\n🔐 ADMIN_ID: {ADMIN_ID or 'не задан'}")

    @bot.message_handler(commands=['reply', 'replay'])
    def reply_cmd(m):
        txt = (m.text or "").strip()
        try:
            print(f"[reply] from={m.from_user.id} text={txt!r}")
        except Exception:
            pass

        if not _is_admin(m.from_user.id):
            bot.reply_to(m, "❗ Команда доступна только администратору.")
            return

        payload = re.sub(r'^/(?:reply|replay)(?:@\w+)?\s*', '', txt, count=1, flags=re.I).strip()
        if not payload:
            bot.reply_to(m, "❗ Формат: /reply <user_id> <текст>\nПример: /reply 5623297755 Спасибо!")
            return

        parts = payload.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(m, "❗ Формат: /reply <user_id> <текст>\nПример: /reply 5623297755 Спасибо!")
            return

        try:
            target_id = int(parts[0])
        except ValueError:
            bot.reply_to(m, "❗ user_id должен быть числом. Пример: /reply 5623297755 Спасибо!")
            return

        body = parts[1].strip()
        if not body:
            bot.reply_to(m, "❗ Пустой текст ответа.")
            return

        try:
            for chunk in _chunk("📩 Ответ от поддержки:\n\n" + body):
                bot.send_message(target_id, chunk)
            bot.reply_to(m, "✅ Отправлено.")
        except apihelper.ApiTelegramException as e:
            desc = ""
            try:
                desc = e.result_json.get("description", "")
            except Exception:
                desc = str(e)
            bot.reply_to(m, f"⚠️ Не удалось отправить.\nПричина: {desc}\n"
                            f"Убедись, что пользователь писал боту и не блокировал его.")
