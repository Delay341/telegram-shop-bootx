# handlers/balance.py
import os, json, threading
from pathlib import Path
from telebot import TeleBot, types
from utils.notify import log_admin

BAL_FILE = Path(os.getenv("BALANCES_FILE", Path(__file__).resolve().parent.parent / "balances.json"))

_BAL_LOCK = threading.Lock()
_BALANCES = {}

def _load_balances():
    global _BALANCES
    if BAL_FILE.exists():
        try:
            _BALANCES = json.loads(BAL_FILE.read_text("utf-8"))
        except Exception:
            _BALANCES = {}
    else:
        _BALANCES = {}

def _save_balances():
    try:
        with _BAL_LOCK:
            BAL_FILE.write_text(json.dumps(_BALANCES, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def get_balance(user_id: int) -> float:
    return float(_BALANCES.get(str(user_id), 0.0))

def add_balance(user_id: int, amount: float):
    with _BAL_LOCK:
        uid = str(user_id)
        _BALANCES[uid] = float(_BALANCES.get(uid, 0.0)) + float(amount)
        _save_balances()

def set_balance(user_id: int, amount: float):
    with _BAL_LOCK:
        _BALANCES[str(user_id)] = float(amount)
        _save_balances()

def register_balance(bot: TeleBot):
    _load_balances()

    @bot.message_handler(commands=['balance'])
    def show_balance(m):
        amount = get_balance(m.from_user.id)
        text = f"💼 Ваш баланс: <b>{amount:.2f} ₽</b>\n\nПополнить: /topup 500\nПосле оплаты: /paid"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("💳 Пополнить баланс", callback_data="balance:pay"))
        bot.reply_to(m, text, reply_markup=kb, parse_mode="HTML")

    @bot.callback_query_handler(func=lambda c: c.data == "balance:pay")
    def balance_pay(c):
        bot.answer_callback_query(c.id)
        pay_link = os.getenv('CARD_DETAILS', '').strip() or '—'
        pay_hint = os.getenv('PAY_INSTRUCTIONS', 'В сообщение к переводу укажите: Ваш @username, услугу и количество')
        text = (
            "💳 Оплата\n\n"
            f"Ссылка для пополнения:\n{pay_link}\n\n"
            f"{pay_hint}\n\n"
            "После оплаты отправьте /paid для проверки.\nЛибо создайте счёт: /topup 500"
        )
        bot.send_message(c.message.chat.id, text)

    ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)

    @bot.message_handler(commands=['balance_set'])
    def balance_set_cmd(m):
        if m.from_user.id != ADMIN_ID:
            return
        parts = (m.text or '').split()
        if len(parts) != 3:
            bot.reply_to(m, "Формат: /balance_set <user_id> <amount>"); return
        try:
            uid = int(parts[1]); amt = float(parts[2].replace(',', '.'))
        except Exception:
            bot.reply_to(m, "Пример: /balance_set 123456789 150.50"); return
        set_balance(uid, amt)
        bot.reply_to(m, f"OK. Баланс {uid} = {get_balance(uid):.2f} ₽")
        log_admin(bot, f"👮 Админ выставил баланс uid={uid} -> {get_balance(uid):.2f} ₽")

    @bot.message_handler(commands=['balance_add'])
    def balance_add_cmd(m):
        if m.from_user.id != ADMIN_ID:
            return
        parts = (m.text or '').split()
        if len(parts) != 3:
            bot.reply_to(m, "Формат: /balance_add <user_id> <amount>"); return
        try:
            uid = int(parts[1]); amt = float(parts[2].replace(',', '.'))
        except Exception:
            bot.reply_to(m, "Пример: /balance_add 123456789 200"); return
        add_balance(uid, amt)
        bot.reply_to(m, f"OK. Баланс {uid} = {get_balance(uid):.2f} ₽ (+{amt})")
        log_admin(bot, f"✅ Пополнение админом uid={uid} +{amt}")
