from telebot import TeleBot, types

def _kb(rows):
    kb = types.InlineKeyboardMarkup()
    for row in rows: kb.row(*row)
    return kb

def register_handlers(bot: TeleBot):
    cfg = bot.CONFIG

    @bot.message_handler(commands=['start'])
    def start(m):
        rows=[]
        for c in cfg.get("categories", []):
            if not c.get("enabled", True): continue
            rows.append([ types.InlineKeyboardButton(c['title'], callback_data=f"cat:{c['id']}") ])
        bot.send_message(m.chat.id, "Выберите категорию 👇", reply_markup=_kb(rows))

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("cat:"))
    def cat_cb(c):
        _, cid = c.data.split(":",1)
        cat = next((x for x in cfg.get("categories", []) if x['id']==cid), None)
        if not cat: bot.answer_callback_query(c.id,"Категория не найдена"); return
        kb = types.InlineKeyboardMarkup()
        for it in cat.get("items", []):
            price = it.get("price","?"); unit_label = "за 1000" if cat.get("unit","per_1000")=="per_1000" else "шт"
            kb.add(types.InlineKeyboardButton(f"{it['title']} — {price} {unit_label}", callback_data=f"item:{cid}:{it['id']}"))
        kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back:root"))
        bot.edit_message_text(chat_id=c.message.chat.id, message_id=c.message.message_id, text=f"Категория: {cat['title']}", reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data=="back:root")
    def back_root(c):
        rows=[]
        for cat in cfg.get("categories", []):
            if not cat.get("enabled", True): continue
            rows.append([ types.InlineKeyboardButton(cat['title'], callback_data=f"cat:{cat['id']}") ])
        bot.edit_message_text(chat_id=c.message.chat.id, message_id=c.message.message_id, text="Выберите категорию 👇", reply_markup=_kb(rows))
