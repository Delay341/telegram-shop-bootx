
import os, json
from telebot import types

UNIT_SIZE = {"per_100": 100, "per_1000": 1000}

EMOJI = {
    "subs": "👥",
    "target": "🎯",
    "real": "👤",
    "views": "👁️",
    "react": "😎",
    "bot": "🤖",
    "back": "⬅️",
    "cart": "🧾",
    "pay": "💳"
}

def money(v):
    return f"{int(v)} ₽" if float(v).is_integer() else f"{float(v):.2f} ₽"

def load_config():
    base = os.path.join(os.path.dirname(__file__), "..", "config", "config.json")
    with open(base, "r", encoding="utf-8") as f:
        return json.load(f)

def register_handlers(bot, config=None):
    if config is None:
        config = load_config()

    SUPPORT = config.get("support_contact", "@Delay34")
    SHOP_NAME = config.get("shop_name", "BoostX")

    SECTIONS = [
        ("cat:tg", "💎 Telegram", [c["id"] for c in config["categories"] if not c["id"].startswith(("yt_","tt_"))]),
        ("cat:yt", "❤️ YouTube", ["yt_followers","yt_likes","yt_views","yt_organic","yt_shorts"]),
        ("cat:tt", "👾 TikTok", ["tt_followers","tt_likes","tt_views","tt_live"]),
    ] for c in config['categories']]),
        ("cat:yt", "❤️ YouTube", []),
        ("cat:tt", "👾 TikTok", []),
    ]} Подписчики", ["subs_no_guarantee", "subs_no_unsubs"]),
        ("cat:target", f"{EMOJI['target']} Таргетированные", ["targeted_subs"]),
        ("cat:real", f"{EMOJI['real']} Реальные", ["real_subs"]),
        ("cat:views", f"{EMOJI['views']} Просмотры", ["views"]),
        ("cat:react", f"{EMOJI['react']} Реакции", ["reactions_slow"]),
        ("cat:bot", f"{EMOJI['bot']} Старты бота", ["bot_starts"]),
    ]
    CAT_TO_SECTION = {}
    for code, title, ids in SECTIONS:
        for cid in ids:
            CAT_TO_SECTION[cid] = (code, title)

    STATE = {}

    def build_sections_menu():
        kb = types.InlineKeyboardMarkup(row_width=2)
        for code, title, _ in SECTIONS:
            kb.add(types.InlineKeyboardButton(title, callback_data=code))
        kb.add(types.InlineKeyboardButton("🧾 Как заказать", callback_data="help:new"),
               types.InlineKeyboardButton("🆘 Поддержка", callback_data="support:ask"))
        return kb

    def build_category_menu(section_code):
        ids = next((ids for code, _title, ids in SECTIONS if code == section_code), [])
        cats = [c for c in config["categories"] if c["id"] in ids]
        kb = types.InlineKeyboardMarkup(row_width=1)
        for cat in cats:
            unit_label = "за 100" if cat["unit"] == "per_100" else "за 1000"
            kb.add(types.InlineKeyboardButton(f"• {cat['title']} ({unit_label})", callback_data=f"open:{cat['id']}"))
        kb.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="back:home"))
        return kb, cats

    def build_items_menu(cat):
        kb = types.InlineKeyboardMarkup(row_width=1)
        unit_label = "за 100" if cat["unit"] == "per_100" else "за 1000"
        for it in cat["items"]:
            price = money(it["price"])
            kb.add(types.InlineKeyboardButton(f"{it['title']} — {price} {unit_label}", callback_data=f"item:{cat['id']}:{it['id']}"))
        kb.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад к категориям", callback_data=f"back:sec_of:{cat['id']}"))
        return kb

    def send_home(chat_id):
        logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png")
        caption = (
            f"<b>{SHOP_NAME}</b>\n"
            "Магазин услуг Telegram для быстрого роста.\n\n"
            "Выберите раздел ниже — бот покажет доступные категории и цены.\n"
            "Оплата вручную: после оформления заказа получите ссылку и инструкции."
        )
        try:
            with open(logo_path, "rb") as pic:
                bot.send_photo(chat_id, pic, caption=caption, reply_markup=build_sections_menu(), parse_mode="HTML")
        except Exception:
            bot.send_message(chat_id, caption, reply_markup=build_sections_menu(), parse_mode="HTML")

    @bot.message_handler(commands=["start","menu"])
    def start(m):
        STATE[m.from_user.id] = {}
        send_home(m.chat.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("cat:"))
    def open_section(call):
        section_code = call.data
        STATE[call.from_user.id] = {"section": section_code}
        _, section_title, _ = next((x for x in SECTIONS if x[0] == section_code), (section_code, section_code, []))
        kb, _cats = build_category_menu(section_code)
        if getattr(call.message, "caption", None):
            bot.edit_message_caption(caption=f"{section_title}\nВыберите категорию:", chat_id=call.message.chat.id,
                                     message_id=call.message.message_id, reply_markup=kb)
        else:
            bot.edit_message_text(f"{section_title}\nВыберите категорию:", call.message.chat.id,
                                  call.message.message_id, reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data == "back:home")
    def back_home(call):
        STATE[call.from_user.id] = {}
        send_home(call.message.chat.id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("open:"))
    def open_category(call):
        cat_id = call.data.split(":")[1]
        cat = next((c for c in config["categories"] if c["id"] == cat_id), None)
        if not cat:
            bot.answer_callback_query(call.id, "Категория не найдена"); return
        st = STATE.get(call.from_user.id, {})
        st["cat_id"] = cat_id
        if "section" not in st:
            st["section"] = CAT_TO_SECTION.get(cat_id, ("cat:subs",""))[0]
        STATE[call.from_user.id] = st
        kb = build_items_menu(cat)
        if getattr(call.message, "caption", None):
            bot.edit_message_caption(caption=f"Категория: <b>{cat['title']}</b>\nВыберите услугу:", chat_id=call.message.chat.id,
                                     message_id=call.message.message_id, reply_markup=kb, parse_mode=None)
        else:
            bot.edit_message_text(f"Категория: <b>{cat['title']}</b>\nВыберите услугу:", call.message.chat.id,
                                  call.message.message_id, parse_mode="HTML", reply_markup=kb)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("back:sec_of:"))
    def back_to_categories(call):
        cat_id = call.data.split(":")[2]
        section_code, section_title = CAT_TO_SECTION.get(cat_id, ("cat:subs","Подписчики"))
        STATE[call.from_user.id] = {"section": section_code}
        kb, _ = build_category_menu(section_code)
        if getattr(call.message, "caption", None):
            bot.edit_message_caption(caption=f"{section_title}\nВыберите категорию:", chat_id=call.message.chat.id,
                                     message_id=call.message.message_id, reply_markup=kb)
        else:
            bot.edit_message_text(f"{section_title}\nВыберите категорию:", call.message.chat.id,
                                  call.message.message_id, reply_markup=kb)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("item:"))
    def pick_item(call):
        _, cat_id, item_id = call.data.split(":")
        cat = next((c for c in config["categories"] if c["id"] == cat_id), None)
        it = next((i for i in cat["items"] if i["id"] == item_id), None)
        unit_size = UNIT_SIZE.get(cat["unit"], 1000)
        st = STATE.get(call.from_user.id, {})
        st.update({"cat_id": cat_id, "item_id": item_id, "unit_size": unit_size})
        if "section" not in st:
            st["section"] = CAT_TO_SECTION.get(cat_id, ("cat:subs",""))[0]
        STATE[call.from_user.id] = st
        bot.answer_callback_query(call.id)
        text = (f"<b>{it['title']}</b>\n"
                f"Тариф: {money(it['price'])} за {unit_size}\n\n"
                f"Введите количество (число). Желательно кратно {unit_size}.")
        bot.send_message(call.message.chat.id, text, parse_mode="HTML")

    @bot.message_handler(func=lambda m: m.from_user.id in STATE and STATE[m.from_user.id].get('item_id') and m.text.strip().isdigit())
    def quantity(m):
        st = STATE.get(m.from_user.id)
        qty = int(m.text.strip())
        cat = next((c for c in config["categories"] if c["id"] == st["cat_id"]), None)
        it = next((i for i in cat["items"] if i["id"] == st["item_id"]), None)
        unit = st["unit_size"]
        total = (qty / unit) * float(it["price"])

        pay_link = "https://www.tinkoff.ru/rm/r_nIutIhQtbX.tRouMxMcdC/kgUL962390"
        instructions = "В сообщении к переводу укажите: @username, услугу, количество"

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад к категориям", callback_data=f"back:sec_of:{cat['id']}"))
        kb.add(types.InlineKeyboardButton("🆘 Поддержка", callback_data="support:ask"))

        text = (
            f"{EMOJI['cart']} <b>Черновик заказа</b>\n"
            f"Услуга: {it['title']}\n"
            f"Категория: {cat['title']}\n"
            f"Количество: {qty}\n"
            f"Тариф: {money(it['price'])} за {unit}\n"
            f"Итого: <b>{money(total)}</b>\n\n"
            f"{EMOJI['pay']} Оплата: {pay_link}\n"
            f"{instructions}\n\n"
            f"Если остались вопросы — напишите в поддержку: {SUPPORT}"
        )
        bot.send_message(m.chat.id, text, reply_markup=kb, parse_mode="HTML")
        STATE[m.from_user.id]["item_id"] = None

    @bot.callback_query_handler(func=lambda c: c.data == "help:new")
    def help_new(call):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад в меню", callback_data="back:home"))
        text = (
            "<b>🧾 Как заказать</b>\n"
            "🟢 1. Выберите раздел и категорию\n"
            "🟢 2. Выберите услугу и укажите количество\n"
            "🟢 3. Оплатите по ссылке, которую пришлёт бот\n"
            f"🟢 4. Отправьте чек и данные заказа в поддержку: {SUPPORT}\n\n"
            "<i>Если остались вопросы — напишите в поддержку.</i>"
        )
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, text, parse_mode="HTML", reply_markup=kb)

    @bot.message_handler(content_types=["text"])
    def fallback(m):
        bot.send_message(m.chat.id, "Нажмите /start, чтобы открыть меню.")

    @bot.message_handler(func=lambda m: STATE.get(m.from_user.id, {}).get('await_support') and m.content_type == 'text')
    def _forward_support(m):
        st = STATE.get(m.from_user.id, {})
        st['await_support'] = False
        STATE[m.from_user.id] = st
        admin_id = int(os.getenv("ADMIN_ID", "0"))
        txt = m.text.strip()
        info = (f"📩 <b>Новый вопрос</b>\n"
                f"От: @{m.from_user.username or '—'} (id {m.from_user.id})\n\n"
                f"<b>Текст:</b>\n{txt}\n\n"
                f"Ответьте /reply {m.from_user.id} ваш_текст")
        try:
            if admin_id:
                bot.send_message(admin_id, info, parse_mode="HTML")
        except Exception:
            pass
        bot.reply_to(m, "✅ Ваше сообщение передано в поддержку. Ответ придёт сюда.")
