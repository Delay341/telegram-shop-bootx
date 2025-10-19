import os, json, threading
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

def load_config():
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "config.json")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)

def money(x):
    return f"{float(x):.2f} ₽"

def _autodelete(bot, chat_id, msg_id, delay=30):
    def _del():
        try:
            bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
    threading.Timer(delay, _del).start()

def register_handlers(bot, config=None):
    if config is None:
        config = load_config()

    SUPPORT = config.get("support_contact", "@Delay34")
    SHOP_NAME = config.get("shop_name", "BoostX")

    SECTIONS = [
        (
            "cat:tg",
            "💎 Telegram",
            [c["id"] for c in config["categories"] if not c["id"].startswith(("yt_", "tt_"))]
        ),
        (
            "cat:yt",
            "❤️ YouTube",
            ["yt_followers", "yt_likes", "yt_views", "yt_organic", "yt_shorts"]
        ),
        (
            "cat:tt",
            "👾 TikTok",
            ["tt_followers", "tt_likes", "tt_views", "tt_live"]
        ),
    ]

    CAT_TO_SECTION = {}
    for code, title, ids in SECTIONS:
        for cid in ids:
            CAT_TO_SECTION[cid] = (code, title)

    STATE = {}

    SECTION_IMAGE = {
        "cat:tg": os.path.join(os.path.dirname(__file__), "..", "assets", "telegram.png"),
        "cat:yt": os.path.join(os.path.dirname(__file__), "..", "assets", "youtube.png"),
        "cat:tt": os.path.join(os.path.dirname(__file__), "..", "assets", "tiktok.png"),
    }


    # Persistence & pricing
    USERS_FILE = os.getenv('USERS_FILE', os.path.join(os.path.dirname(__file__), '..', 'users.json'))
    ORDERS_FILE = os.getenv('ORDERS_FILE', os.path.join(os.path.dirname(__file__), '..', 'orders.json'))
    PRICING_MULT = float(config.get('pricing_multiplier', 2.0))
    PROMO = config.get('promo', {})

    # Payment from env with sensible defaults
    DEFAULT_CARD = "https://www.tinkoff.ru/rm/r_nIutIhQtbX.tRouMxMcdC/kgUL962390"
    DEFAULT_NOTE = "В сообщение к переведу укажите: Ваш @username, услугу, количество"
    CARD_DETAILS = os.getenv('CARD_DETAILS', DEFAULT_CARD)
    PAY_INSTRUCTIONS = os.getenv('PAY_INSTRUCTIONS', DEFAULT_NOTE)

    def build_sections_menu():
        kb = types.InlineKeyboardMarkup(row_width=2)
        for code, title, _ in SECTIONS:
            kb.add(types.InlineKeyboardButton(title, callback_data=code))
        kb.add(types.InlineKeyboardButton("💰 Баланс", callback_data="menu:balance"))
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
            price = money(it["price"] * PRICING_MULT)
            kb.add(types.InlineKeyboardButton(f"{it['title']} — {price} {unit_label}", callback_data=f"item:{cat['id']}:{it['id']}"))
        kb.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад к категориям", callback_data=f"back:sec_of:{cat['id']}"))
        return kb

    def send_home(chat_id):
        caption = (
            f"<b>{SHOP_NAME}</b>\n"
            "Магазин услуг для быстрого роста.\n\n"
            "Выберите раздел ниже — бот покажет доступные категории и цены.\n"
            "Оплата вручную: после оформления заказа получите ссылку и инструкции."
        )
        try:
            with open(os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png"), "rb") as pic:
                bot.send_photo(chat_id, pic, caption=caption, reply_markup=build_sections_menu(), parse_mode="HTML")
        except Exception:
            bot.send_message(chat_id, caption, reply_markup=build_sections_menu(), parse_mode="HTML")

    @bot.message_handler(commands=["start","menu"])
    def start(m):
        STATE[m.from_user.id] = {}
        # save user id
        try:
            os.makedirs(os.path.join(os.path.dirname(__file__), '..'), exist_ok=True)
            existing = []
            if os.path.exists(USERS_FILE):
                existing = json.loads(open(USERS_FILE,'r',encoding='utf-8').read() or '[]')
            if m.from_user.id not in existing:
                existing.append(m.from_user.id)
                open(USERS_FILE,'w',encoding='utf-8').write(json.dumps(existing, ensure_ascii=False, indent=2))
        except Exception:
            pass
        send_home(m.chat.id)

    @bot.callback_query_handler(func=lambda c: c.data == "support:ask")
    def support_ask(call):
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "✏️ Напишите ваш вопрос — я передам его в поддержку. Используйте /support в любой момент.")
        st = STATE.get(call.from_user.id, {})
        st["await_support"] = True
        STATE[call.from_user.id] = st

    @bot.callback_query_handler(func=lambda c: c.data.startswith("cat:"))
    def open_section(call):
        section_code = call.data
        STATE[call.from_user.id] = {"section": section_code}
        _, section_title, _ = next((x for x in SECTIONS if x[0] == section_code), (section_code, section_code, []))
        kb, _cats = build_category_menu(section_code)
        try:
            img = SECTION_IMAGE.get(section_code)
            if img and os.path.exists(img):
                with open(img, "rb") as pic:
                    bot.send_photo(call.message.chat.id, pic, caption=f"{section_title}\nВыберите категорию:", reply_markup=kb, parse_mode="HTML")
            else:
                bot.send_message(call.message.chat.id, f"{section_title}\nВыберите категорию:", reply_markup=kb)
        except Exception:
            bot.send_message(call.message.chat.id, f"{section_title}\nВыберите категорию:", reply_markup=kb)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("open:"))
    def open_category(call):
        _, cat_id = call.data.split(":")
        cat = next((c for c in config["categories"] if c["id"] == cat_id), None)
        if not cat:
            bot.answer_callback_query(call.id, "Категория не найдена", show_alert=True)
            return
        kb = build_items_menu(cat)
        text = f"<b>{cat['title']}</b>\nВыберите услугу:"
        try:
            sec_code = CAT_TO_SECTION.get(cat_id, ("cat:tg",""))[0]
            img = SECTION_IMAGE.get(sec_code)
            if img and os.path.exists(img):
                with open(img, "rb") as pic:
                    bot.send_photo(call.message.chat.id, pic, caption=text, reply_markup=kb, parse_mode="HTML")
            else:
                bot.send_message(call.message.chat.id, text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            bot.send_message(call.message.chat.id, text, reply_markup=kb, parse_mode="HTML")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("item:"))
    def pick_item(call):
        _, cat_id, item_id = call.data.split(":")
        cat = next((c for c in config["categories"] if c["id"] == cat_id), None)
        it = next((i for i in cat["items"] if i["id"] == item_id), None)
        unit_size = UNIT_SIZE.get(cat["unit"], 1000)
        st = STATE.get(call.from_user.id, {})
        st.update({"cat_id": cat_id, "item_id": item_id, "unit_size": unit_size, "username": call.from_user.username})
        if "section" not in st:
            st["section"] = CAT_TO_SECTION.get(cat_id, ("cat:tg",""))[0]
        STATE[call.from_user.id] = st
        bot.answer_callback_query(call.id)
        text = (f"<b>{it['title']}</b>\n"
                f"Тариф: {money(it['price'] * PRICING_MULT)} за {unit_size}\n\n"
                f"Введите количество (число) | Минимальный заказ 10 шт.")
        msg = bot.send_message(call.message.chat.id, text, parse_mode="HTML")
        _autodelete(bot, call.message.chat.id, msg.message_id, 40)

    @bot.message_handler(func=lambda m: m.from_user.id in STATE and STATE[m.from_user.id].get('item_id') and (m.text or '').strip().isdigit())
    def quantity(m):
        st = STATE.get(m.from_user.id)
        qty = int((m.text or '').strip())
        if qty < 10:
            bot.reply_to(m, 'Минимальный заказ — 10. Введите количество заново.')
            return
        st['qty'] = qty
        STATE[m.from_user.id] = st
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton('Пропустить', callback_data='promo:skip'))
        bot.send_message(m.chat.id, 'Если есть промокод — отправьте его одним сообщением. Иначе нажмите «Пропустить».', reply_markup=kb)
        return

    @bot.callback_query_handler(func=lambda c: c.data in ('promo:skip',))
    def promo_skip(call):
        st = STATE.get(call.from_user.id, {})
        _finalize_order(call.message.chat.id, call.from_user.id, st)
        bot.answer_callback_query(call.id)

    @bot.message_handler(func=lambda m: m.from_user.id in STATE and STATE[m.from_user.id].get('qty') and not (m.text or '').strip().isdigit())
    def promo_entered(m):
        st = STATE.get(m.from_user.id, {})
        st['promo'] = (m.text or '').strip().upper()
        STATE[m.from_user.id] = st
        _finalize_order(m.chat.id, m.from_user.id, st)

    def _finalize_order(chat_id, user_id, st):
        cat = next((c for c in config["categories"] if c["id"] == st["cat_id"]), None)
        it = next((i for i in cat["items"] if i["id"] == st["item_id"]), None)
        qty = int(st.get("qty", 0))
        unit = int(st.get("unit_size", 1000))
        units = qty / unit

        # pricing with multiplier & promo
        price_base = float(it["price"]) * float(PRICING_MULT)
        promo_factor = 1.0
        promo_used = st.get("promo")
        # merge config PROMO with file promos
        file_promos = {}
        try:
            import json as _json
            pf = os.path.join(os.path.dirname(__file__), '..', 'promos.json')
            if os.path.exists(pf):
                file_promos = _json.loads(open(pf,'r',encoding='utf-8').read() or '{}')
        except Exception:
            pass
        all_promos = {}
        all_promos.update(PROMO)
        all_promos.update(file_promos)
        if promo_used and promo_used in all_promos:
            promo_factor = float(all_promos[promo_used])
        total = round(price_base * units * promo_factor, 2)

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data=f"back:sec_of:{st['cat_id']}"))
        text = (
            f"<b>Заказ</b>\n"
            f"Услуга: {it['title']}\n"
            f"Количество: {qty} (шаг {unit})\n"
            f"Цена за {unit}: {money(price_base)} (множитель x{PRICING_MULT})\n"
            f"Промо: {promo_used or '—'}\n"
            f"К оплате: <b>{money(total)}</b>\n\n"
            f"<b>Оплата:</b>\n{CARD_DETAILS}\n\n"
            f"{PAY_INSTRUCTIONS}"
        )
        msg = bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)
        _autodelete(bot, chat_id, msg.message_id, 120)

        # Save order to ORDERS_FILE
        try:
            os.makedirs(os.path.join(os.path.dirname(__file__), '..'), exist_ok=True)
            orders = []
            if os.path.exists(ORDERS_FILE):
                orders = json.loads(open(ORDERS_FILE,'r',encoding='utf-8').read() or '[]')
            orders.append({
                "ts": int(__import__('time').time()),
                "user_id": user_id,
                "username": st.get("username"),
                "cat_id": st["cat_id"],
                "item_id": st["item_id"],
                "qty": qty,
                "unit": unit,
                "units": units,
                "price_per_unit": price_base,
                "promo": promo_used or "",
                "total": total
            })
            open(ORDERS_FILE,'w',encoding='utf-8').write(json.dumps(orders, ensure_ascii=False, indent=2))
        except Exception:
            pass

        STATE[user_id] = {"section": st.get("section")}

    @bot.callback_query_handler(func=lambda c: c.data.startswith("back:sec_of:"))
    def back_to_section(call):
        _, _, cat_id = call.data.split(":")
        sec_code = CAT_TO_SECTION.get(cat_id, ("cat:tg", ""))[0]
        kb, _ = build_category_menu(sec_code)
        _, sec_title, _ = next((x for x in SECTIONS if x[0] == sec_code), (sec_code, sec_code, []))
        try:
            bot.edit_message_text(f"{sec_title}\nВыберите категорию:", call.message.chat.id,
                                  call.message.message_id, reply_markup=kb)
        except Exception:
            bot.send_message(call.message.chat.id, f"{sec_title}\nВыберите категорию:", reply_markup=kb)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "back:home")
    def back_home(call):
        send_home(call.message.chat.id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "help:new")
    def help_new(call):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="back:home"))
        text = (
            "<b>🧾 Как заказать</b>\n"
            "🟢 1. Выберите раздел и категорию\n"
            "🟢 2. Выберите услугу и укажите количество\n"
            "🟢 3. Оплатите по ссылке/реквизитам, которые пришлёт бот\n"
            f"🟢 4. Отправьте чек и данные заказа в поддержку: {SUPPORT}\n\n"
            "<i>Если остались вопросы — напишите в поддержку.</i>"
        )
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, text, parse_mode="HTML", reply_markup=kb)

    @bot.message_handler(func=lambda m: STATE.get(m.from_user.id, {}).get('await_support') and m.content_type == 'text')
    def _forward_support(m):
        st = STATE.get(m.from_user.id, {})
        st['await_support'] = False
        STATE[m.from_user.id] = st
        admin_id = int(os.getenv("ADMIN_ID", "0"))
        txt = (m.text or "").strip()
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

    @bot.message_handler(content_types=["text"])
    def fallback(m):
        if m.text.startswith("/"):
            return
        bot.send_message(m.chat.id, "Нажмите /start, чтобы открыть меню.")
