
from telebot import TeleBot, types
from utils.db import fetch_one

def _kb(rows):
    kb = types.InlineKeyboardMarkup()
    for row in rows:
        kb.row(*row)
    return kb

def _get_balance(user_id: int) -> float:
    row = fetch_one("SELECT balance FROM users WHERE user_id=?", (user_id,))
    return float(row["balance"]) if row else 0.0

def register_handlers(bot: TeleBot):
    cfg = bot.CONFIG

    @bot.message_handler(commands=['start'])
    def start(m):
        rows = []
        for c in cfg.get("categories", []):
            if not c.get("enabled", True):
                continue
            rows.append([ types.InlineKeyboardButton(c['title'], callback_data=f"cat:{c['id']}") ])
        rows.append([ types.InlineKeyboardButton("💰 Баланс", callback_data="balance:show") ])
        bot.send_message(m.chat.id, "Выберите категорию 👇", reply_markup=_kb(rows))

    @bot.callback_query_handler(func=lambda c: c.data == "balance:show")
    def balance_show(c):
        bal = _get_balance(c.from_user.id)
        bot.answer_callback_query(c.id)
        bot.send_message(c.from_user.id, f"💰 Ваш баланс: <b>{bal:.2f} ₽</b>", parse_mode="HTML")

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("cat:"))
    def cat_cb(c):
        _, cid = c.data.split(":",1)
        cat = next((x for x in cfg.get("categories", []) if x['id']==cid), None)
        if not cat:
            bot.answer_callback_query(c.id,"Категория не найдена")
            return
        kb = types.InlineKeyboardMarkup()
        for it in cat.get("items", []):
            price = it.get("price","?")
            unit_label = "за 1000" if cat.get("unit","per_1000")=="per_1000" else "шт"
            kb.add(types.InlineKeyboardButton(f"{it['title']} — {price} {unit_label}", callback_data=f"item:{cid}:{it['id']}"))
        kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back:root"))
        bot.edit_message_text(chat_id=c.message.chat.id, message_id=c.message.message_id, text=f"Категория: {cat['title']}", reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data=="back:root")
    def back_root(c):
        rows=[]
        for cat in cfg.get("categories", []):
            if not cat.get("enabled", True):
                continue
            rows.append([ types.InlineKeyboardButton(cat['title'], callback_data=f"cat:{cat['id']}") ])
        rows.append([ types.InlineKeyboardButton("💰 Баланс", callback_data="balance:show") ])
        bot.edit_message_text(chat_id=c.message.chat.id, message_id=c.message.message_id, text="Выберите категорию 👇", reply_markup=_kb(rows))
