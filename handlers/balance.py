import time, random, os
from telebot import TeleBot
from utils.db import fetch_one, execute, execute_with_lastrowid
from utils.notify import log_admin

PAYMENT_LINK = os.getenv("CARD_DETAILS","").strip()
PAY_HINT = os.getenv("PAY_INSTRUCTIONS","В сообщение к переводу укажите: Ваш @username, услугу, количество")

def _ensure_user(uid, uname):
    if fetch_one("SELECT 1 FROM users WHERE user_id=?", (uid,)) is None:
        execute("INSERT INTO users(user_id,username,balance) VALUES(?,?,0)", (uid, uname or ""))

def add_balance(uid, amount: float):
    execute("UPDATE users SET balance = COALESCE(balance,0)+? WHERE user_id=?", (float(amount), uid))

def get_balance(uid) -> float:
    row = fetch_one("SELECT balance FROM users WHERE user_id=?", (uid,))
    return float(row["balance"]) if row else 0.0

def _generate_tail(base):
    tail = random.randint(11,97)
    unique = round(float(base) + tail/100.0, 2)
    code = f"BX{int(time.time())}{tail}"
    return unique, code

def register_balance(bot: TeleBot):
    @bot.message_handler(commands=['balance'])
    def balance_cmd(m):
        _ensure_user(m.from_user.id, m.from_user.username)
        bal = get_balance(m.from_user.id)
        kb = None
        try:
            from telebot import types
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("💸 Пополнить", callback_data="balance:pay"))
        except Exception:
            pass
        bot.reply_to(m, f"💰 Ваш баланс: <b>{bal:.2f} ₽</b>", parse_mode="HTML", reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data=="balance:pay")
    def balance_pay(c):
        text = "💳 Оплата

"
        if PAYMENT_LINK: text += f"Ссылка: {PAYMENT_LINK}
"
        if PAY_HINT: text += f"{PAY_HINT}

"
        text += "После перевода используйте /paid или создайте счёт через /topup <сумма>."
        bot.answer_callback_query(c.id)
        bot.send_message(c.from_user.id, text)

    @bot.message_handler(commands=['topup'])
    def topup_cmd(m):
        parts = (m.text or "").split()
        if len(parts)!=2:
            bot.reply_to(m, "Формат: /topup <сумма>")
            return
        try:
            base = float(parts[1].replace(',','.'))
        except Exception:
            bot.reply_to(m, "Введите число, например: /topup 500")
            return
        unique, code = _generate_tail(base)
        pid = execute_with_lastrowid(
            "INSERT INTO pending_topups(user_id,order_amount,code,base_amount,created_at) VALUES(?,?,?,?,?)",
            (m.from_user.id, unique, code, base, int(time.time()))
        )
        link = PAYMENT_LINK
        bot.reply_to(m, f"💳 Пополнение #{pid}
Сумма к переводу: <b>{unique:.2f} ₽</b>
Ссылка: {link}
Комментарий: <code>{code}</code>
После перевода нажмите /paid", parse_mode="HTML")
        log_admin(bot, f"🧾 Заявка на пополнение #{pid} от @{m.from_user.username or m.from_user.id}: base={base}, unique={unique}, code={code}")
