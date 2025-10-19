
import os, time, random
from telebot import TeleBot, types
from utils.notify import log_admin
from .balance import add_balance

_state = {}

def _unique_amount(base: float):
    tail = random.randint(11,97)/100.0
    return round(float(base)+tail, 2)

def register_payments(bot: TeleBot):
    @bot.message_handler(commands=['pay'])
    def pay_info(m):
        text = "💳 Оплата\n\n"
        pay_link = os.getenv('CARD_DETAILS','').strip()
        pay_hint = os.getenv('PAY_INSTRUCTIONS','В сообщение к переводу укажите: Ваш @username, услугу и количество')
        if pay_link: text += f"Ссылка: {pay_link}\n"
        if pay_hint: text += f"{pay_hint}\n\n"
        text += "После перевода отправьте /paid и прикрепите данные (текст/фото)."
        bot.reply_to(m, text)

    @bot.message_handler(commands=['topup'])
    def topup(m):
        parts = (m.text or '').split()
        if len(parts)!=2:
            bot.reply_to(m, "Формат: /topup <сумма>"); return
        try:
            base = float(parts[1].replace(',','.'))
        except Exception:
            bot.reply_to(m, "Введите число, например: /topup 500"); return
        unique = _unique_amount(base)
        code = f"BX{int(time.time())}"
        pay_link = os.getenv('CARD_DETAILS','—')
        text = f"🧾 Счёт на пополнение\nСумма к переводу: <b>{unique:.2f} ₽</b>\nКомментарий: <code>{code}</code>\nСсылка: {pay_link}\nПосле оплаты нажмите /paid"
        bot.reply_to(m, text, parse_mode="HTML")
        log_admin(bot, f"🧾 Новый счёт от @{m.from_user.username or m.from_user.id}: base={base}, unique={unique}, code={code}")

    @bot.message_handler(commands=['paid'])
    def paid_start(m):
        _state[m.from_user.id] = {'step':'amount'}
        bot.reply_to(m, "Укажите сумму оплаты (число).")

    @bot.message_handler(func=lambda msg: _state.get(msg.from_user.id,{}).get('step')=='amount')
    def paid_amount(m):
        try:
            amount = float(m.text.replace(',','.'))
            _state[m.from_user.id] = {'step':'details','amount':amount}
            bot.reply_to(m, "Опишите, за что оплата: услуга и количество. Можно прикрепить скрин чека.")
        except Exception:
            bot.reply_to(m, "Введите число, например: 499 или 499.00")

    @bot.message_handler(func=lambda msg: _state.get(msg.from_user.id,{}).get('step')=='details', content_types=['text','photo'])
    def paid_details(m):
        rec = _state.get(m.from_user.id,{})
        if not rec: return
        amount = rec.get('amount',0)
        details = m.caption or m.text or "(без текста)"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"payok:{m.from_user.id}:{amount}"),
               types.InlineKeyboardButton("❌ Отклонить", callback_data=f"payno:{m.from_user.id}:{amount}"))
        admin_chat = int(os.getenv("ADMIN_LOG_CHAT_ID", os.getenv("ADMIN_ID","0") or 0))
        if m.photo:
            fid = m.photo[-1].file_id
            bot.send_photo(admin_chat, fid, caption=f"💸 Новый платёж\nОт: @{m.from_user.username or m.from_user.id}\nID: {m.from_user.id}\nСумма: {amount}\nДетали: {details}", reply_markup=kb)
        else:
            log_admin(bot, f"💸 Новый платёж\nОт: @{m.from_user.username or m.from_user.id}\nID: {m.from_user.id}\nСумма: {amount}\nДетали: {details}")
            bot.send_message(admin_chat, "Выберите действие:", reply_markup=kb)
        bot.reply_to(m, "✅ Заявка на проверку оплаты отправлена. Ожидайте подтверждения.")
        _state.pop(m.from_user.id, None)

    @bot.callback_query_handler(func=lambda c: c.data and (c.data.startswith("payok:") or c.data.startswith("payno:")))
    def paid_review(c):
        parts = c.data.split(":"); act, uid, amount = parts[0], int(parts[1]), parts[2]
        if str(c.from_user.id) != os.getenv("ADMIN_ID",""):
            bot.answer_callback_query(c.id, "Только администратор может подтверждать", show_alert=True); return
        if act=="payok":
            add_balance(uid, float(amount))
            bot.answer_callback_query(c.id, "Оплата подтверждена ✅", show_alert=False)
            bot.send_message(uid, f"✅ Оплата на сумму {amount} подтверждена. Спасибо!")
            log_admin(bot, f"✅ Оплата подтверждена админом. Пользователь {uid}, сумма {amount}")
        else:
            bot.answer_callback_query(c.id, "Оплата отклонена ❌", show_alert=False)
            bot.send_message(uid, "❌ Оплата отклонена. Напишите, если нужна помощь.")
            log_admin(bot, f"❌ Оплата отклонена админом. Пользователь {uid}, сумма {amount}")
