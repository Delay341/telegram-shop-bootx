import os, json, threading
from pathlib import Path
from telebot import TeleBot, types
from utils.notify import log_admin

PAY_URL = os.getenv("PAY_URL", "https://www.tinkoff.ru/rm/r_nIutIhQtbX.tRouMxMcdC/kgUL962390")
BAL_FILE = Path(os.getenv("BALANCES_FILE", Path(__file__).resolve().parent.parent / "balances.json"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
ADMIN_LOG_CHAT_ID = int(os.getenv("ADMIN_LOG_CHAT_ID", "0") or 0)

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

def set_balance(user_id: int, amount: float):
    with _BAL_LOCK:
        _BALANCES[str(user_id)] = float(amount)
        _save_balances()

def add_balance(user_id: int, amount: float):
    with _BAL_LOCK:
        uid = str(user_id)
        _BALANCES[uid] = float(_BALANCES.get(uid, 0.0)) + float(amount)
        _save_balances()

def send_balance_view(bot: TeleBot, chat_id: int, user_id: int):
    amt = get_balance(user_id)
    text = (
        f"💰 <b>Ваш баланс</b>: <b>{amt:.2f} ₽</b>\n\n"
        "Чтобы пополнить, нажмите «💳 Пополнить», выберите сумму и совершите перевод.\n"
        "После оплаты — нажмите «Я оплатил ✅»."
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Пополнить", url=PAY_URL))
    kb.add(types.InlineKeyboardButton("Я оплатил ✅", callback_data="balance:paid"))
    bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")

def register_balance(bot: TeleBot):
    _load_balances()

    @bot.message_handler(commands=['balance'])
    def balance_cmd(m):
        send_balance_view(bot, m.chat.id, m.from_user.id)

    @bot.callback_query_handler(func=lambda c: c.data == "menu:balance")
    def menu_balance(c):
        bot.answer_callback_query(c.id)
        send_balance_view(bot, c.message.chat.id, c.from_user.id)

    @bot.callback_query_handler(func=lambda c: c.data == "balance:paid")
    def balance_paid(c):
        bot.answer_callback_query(c.id, "Принято! Проверим перевод и зачислим баланс.")
        uid = c.from_user.id
        uname = c.from_user.username or "—"
        bot.send_message(c.message.chat.id, "✅ Заявка на проверку отправлена. Обычно 5–15 минут.")
        cmd_hint = f"/balance_add {uid} <сумма>"
        admin_text = (
            "💳 <b>Новая заявка на пополнение</b>\n"
            f"UID: <code>{uid}</code>\n"
            f"User: @{uname}\n\n"
            f"После проверки зачислите:\n<code>{cmd_hint}</code>"
        )
        try:
            if ADMIN_LOG_CHAT_ID:
                bot.send_message(ADMIN_LOG_CHAT_ID, admin_text, parse_mode="HTML")
            elif ADMIN_ID:
                bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML")
        except Exception:
            pass
