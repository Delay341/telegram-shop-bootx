# handlers/autodebit.py
import os, json, time
from pathlib import Path
from telebot import TeleBot
from .balance import get_balance, add_balance, set_balance
from utils.notify import log_admin

ORDERS_FILE = Path(os.getenv("ORDERS_FILE", Path(__file__).resolve().parent.parent / "orders.json"))
ORDERS_FILE.parent.mkdir(parents=True, exist_ok=True)

def _append_order(order: dict):
    try:
        data = []
        if ORDERS_FILE.exists():
            data = json.loads(ORDERS_FILE.read_text("utf-8"))
            if not isinstance(data, list):
                data = []
        data.append(order)
        ORDERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def register_autodebit(bot: TeleBot):
    @bot.message_handler(commands=['charge'])
    def charge_cmd(m):
        """
        /charge <amount> <desc...>
        Списывает <amount> ₽ с баланса пользователя и создаёт заказ типа 'balance_charge'.
        Пример: /charge 299 Пак подписчиков Instagram 300
        """
        parts = (m.text or "").split()
        if len(parts) < 2:
            bot.reply_to(m, "Формат: /charge <amount> <описание>\nНапример: /charge 299 Пак подписчиков Instagram 300")
            return
        try:
            amount = float(parts[1].replace(",", "."))
        except Exception:
            bot.reply_to(m, "Сумма должна быть числом. Пример: /charge 199.90 Пак TikTok 1000"); return
        desc = " ".join(parts[2:]).strip() or "Покупка из баланса"
        uid = m.from_user.id
        bal = get_balance(uid)
        if bal < amount:
            bot.reply_to(m, f"Недостаточно средств. Баланс: {bal:.2f} ₽, требуется: {amount:.2f} ₽")
            return
        # списываем
        set_balance(uid, bal - amount)
        order = {
            "type": "balance_charge",
            "user_id": uid,
            "username": m.from_user.username,
            "amount": amount,
            "description": desc,
            "ts": int(time.time())
        }
        _append_order(order)
        bot.reply_to(m, f"✅ Оплата с баланса прошла успешно.\nСписано: {amount:.2f} ₽\nТекущий баланс: {get_balance(uid):.2f} ₽")
        try:
            log_admin(bot, f"💳 Списание с баланса: uid={uid} @{m.from_user.username or '—'} -{amount:.2f} ₽\n{desc}")
        except Exception:
            pass
