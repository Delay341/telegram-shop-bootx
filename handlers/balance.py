
import os
from telebot import TeleBot, types
from utils.notify import log_admin

# Простая in-memory модель (совместима с существующим add_balance)
BALANCES = {}

def get_balance(user_id):
    return BALANCES.get(user_id, 0.0)

def add_balance(user_id, amount):
    BALANCES[user_id] = get_balance(user_id) + float(amount)

def register_balance(bot: TeleBot):
    @bot.message_handler(commands=['balance'])
    def show_balance(m):
        uid = m.from_user.id
        balance = get_balance(uid)
        text = f"\uD83D\uDCB0 Ваш баланс: {balance:.2f} ₽\n\n"
        text += "Чтобы пополнить баланс, нажмите кнопку ниже."
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("\uD83D\uDCB3 Пополнить баланс", callback_data="balance:pay"))
        bot.reply_to(m, text, reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data == "balance:pay")
    def balance_pay(c):
        bot.answer_callback_query(c.id)
        pay_link = os.getenv('CARD_DETAILS', '').strip() or '—'
        pay_hint = os.getenv('PAY_INSTRUCTIONS', 'В сообщение к переводу укажите: Ваш @username, сумму и ID')
        text = "💳 Оплата\n\n"
        text += f"Ссылка для пополнения:\n{pay_link}\n\n"
        text += f"{pay_hint}\n\n"
        text += "После оплаты отправьте /paid для проверки."
        bot.send_message(c.message.chat.id, text)
