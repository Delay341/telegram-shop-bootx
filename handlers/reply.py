import os, re
from telebot import TeleBot, apihelper
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
def _chunk(s, n=4096):
    for i in range(0, len(s), n): yield s[i:i+n]
def _is_admin(uid: int) -> bool: return ADMIN_ID and uid == ADMIN_ID
def register_reply_handler(bot: TeleBot):
    @bot.message_handler(commands=['whoami'])
    def whoami(m): bot.reply_to(m, f"👤 ID: {m.from_user.id}\n🔐 ADMIN_ID: {ADMIN_ID or 'не задан'}")
    @bot.message_handler(commands=['reply','replay'])
    def reply_cmd(m):
        if not _is_admin(m.from_user.id):
            bot.reply_to(m, "❗ Команда доступна только администратору."); return
        payload = re.sub(r'^/(?:reply|replay)(?:@\w+)?\s*','', (m.text or ''), 1, flags=re.I).strip()
        parts = payload.split(maxsplit=1)
        if len(parts)<2: bot.reply_to(m,"Формат: /reply <user_id> <текст>"); return
        try: uid = int(parts[0])
        except: bot.reply_to(m,"user_id должен быть числом"); return
        body = parts[1].strip()
        try:
            for ch in _chunk("📩 Ответ от поддержки:\n\n"+body): bot.send_message(uid, ch)
            bot.reply_to(m,"✅ Отправлено.")
        except apihelper.ApiTelegramException as e:
            desc = getattr(e,'result_json',{}).get('description', str(e))
            bot.reply_to(m, f"⚠️ Не удалось отправить: {desc}")
