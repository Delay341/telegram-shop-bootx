# -*- coding: utf-8 -*-
from __future__ import annotations
import os, json
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, Defaults, ConversationHandler, MessageHandler, filters
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CATALOG_PATH = Path("config/config.json")


def load_catalog() -> Dict[str, Any]:
    if not CATALOG_PATH.exists():
        return {"pricing_multiplier": 1.0, "categories": []}
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        data.setdefault("pricing_multiplier", 1.0)
        data.setdefault("categories", [])
        return data
    except Exception as e:
        print("Ошибка загрузки каталога:", e)
        return {"pricing_multiplier": 1.0, "categories": []}


def _format_price(price: float, unit: str, mult: float) -> str:
    p = float(price) * float(mult)
    tail = "за 1000" if unit == "per_1000" else "за 100"
    return f"{p:.2f} ₽ {tail}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Добро пожаловать в <b>BoostX</b>!\n\n"
        "Нажмите «Каталог», чтобы выбрать услугу и оформить заказ.\n"
        "Команды: /catalog, /services, /balance, /topup, /help"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Каталог", callback_data="catalog")],
        [InlineKeyboardButton("💳 Баланс", callback_data="balance")],
    ])
    if update.message:
        await update.message.reply_html(text, reply_markup=kb)
    elif update.callback_query:
        await update.callback_query.message.reply_html(text, reply_markup=kb)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 Команды:\n"
        "/start — приветствие\n"
        "/catalog — каталог услуг (или кнопка «Каталог»)\n"
        "/services — то же, что /catalog\n"
        "/balance — баланс\n"
        "/topup <сумма> — пополнить баланс\n"
        "/confirm_payment <invoice_id> — подтверждение оплаты (админ)\n"
        "/ping — проверка ответа бота\n"
        "/debug — сведения о сборке/каталоге\n"
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")


async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok_token = bool(BOT_TOKEN and len(BOT_TOKEN) > 20)
    cat = load_catalog()
    await update.message.reply_text(
        "🤖 Debug:\n"
        f"Token set: {ok_token}\n"
        f"Products file: {'exists' if CATALOG_PATH.exists() else 'missing'}\n"
        f"Categories: {len(cat.get('categories', []))}\n"
        f"Multiplier: {cat.get('pricing_multiplier', 1.0)}"
    )


async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    data = load_catalog()
    cats = data.get("categories", [])
    if not cats:
        target = query.message if query else update.message
        await target.reply_text("Каталог временно пуст.")
        return

    buttons = [
        [InlineKeyboardButton(c.get("title", "Категория"), callback_data=f"cat_{i}")]
        for i, _ in enumerate(cats)
    ]
    kb = InlineKeyboardMarkup(buttons)
    target = query.message if query else update.message
    await target.reply_html("<b>📋 Каталог BoostX</b>\n\nВыберите категорию:", reply_markup=kb)


async def show_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_catalog()
    cats = data.get("categories", [])
    try:
        idx = int(query.data.split("_")[1])
    except Exception:
        await query.answer("Ошибка категории")
        return
    if idx < 0 or idx >= len(cats):
        await query.answer("Категория не найдена")
        return
    cat = cats[idx]
    title = cat.get("title", "Категория")
    unit = cat.get("unit", "per_1000")
    mult = float(data.get("pricing_multiplier", 1.0))
    items = cat.get("items", [])

    rows = []
    for i, item in enumerate(items):
        price = _format_price(item.get("price", 0), unit, mult)
        label = f"{item.get('title','Услуга')} — {price}"
        rows.append([InlineKeyboardButton(label[:64], callback_data=f"item_{idx}_{i}")])
    rows.append([InlineKeyboardButton("⬅️ Назад к категориям", callback_data="catalog")])

    await query.message.reply_html(
        f"<b>{title}</b>\nВыберите услугу:", reply_markup=InlineKeyboardMarkup(rows)
    )


LINK, QTY = range(2)


async def order_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, cat_idx, item_idx = query.data.split("_")
    cat_idx, item_idx = int(cat_idx), int(item_idx)

    data = load_catalog()
    try:
        cat = data["categories"][cat_idx]
        item = cat["items"][item_idx]
    except Exception:
        await query.message.reply_text("Ошибка выбора услуги.")
        return ConversationHandler.END

    context.user_data["order"] = {
        "cat_idx": cat_idx,
        "item_idx": item_idx,
        "unit": cat.get("unit", "per_1000"),
        "mult": float(data.get("pricing_multiplier", 1.0)),
        "title": item.get("title", "Услуга"),
        "price": float(item.get("price", 0)),
        "service_id": item.get("service_id"),
    }
    await query.message.reply_text("🔗 Отправьте ссылку (URL), на которую оформляем заказ:")
    return LINK


async def order_get_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = (update.message.text or "").strip()
    if not (link.startswith("http://") or link.startswith("https://") or ".com" in link or ".ru" in link):
        await update.message.reply_text("Похоже, это не ссылка. Отправьте корректный URL:")
        return LINK
    context.user_data["order"]["link"] = link
    await update.message.reply_text("🔢 Укажите количество (целое число):")
    return QTY


async def order_get_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from boostx_ext.balance import get_balance, set_balance
    from handlers.order_looksmm import create_looksmm_order, compute_cost

    txt = (update.message.text or "").strip()
    if not txt.isdigit():
        await update.message.reply_text("Количество должно быть целым числом. Введите ещё раз:")
        return QTY

    qty = int(txt)
    if qty <= 0:
        await update.message.reply_text("Количество должно быть больше 0. Введите ещё раз:")
        return QTY

    info = context.user_data.get("order", {})
    service_id = info.get("service_id")
    if not service_id:
        await update.message.reply_text("Эта позиция пока не поддерживает авто-заказ. Сообщи администратору.")
        return ConversationHandler.END

    cost = compute_cost(price=info["price"], unit=info["unit"], mult=info["mult"], qty=qty)

    uid = update.effective_user.id
    bal = get_balance(uid)
    if bal < cost:
        await update.message.reply_text(
            f"Недостаточно средств. Нужно ~{cost:.2f} ₽, на балансе {bal:.2f} ₽.\n"
            f"Пополнить: /topup <сумма>"
        )
        return ConversationHandler.END

    set_balance(uid, bal - cost)

    try:
        resp = await create_looksmm_order(service_id=service_id, link=info["link"], qty=qty)
        order_id = resp
        from boostx_ext.orders import append_order
        append_order({
            "user_id": uid,
            "title": info["title"],
            "service_id": service_id,
            "link": info["link"],
            "qty": qty,
            "cost": float(f"{cost:.2f}"),
            "provider_order_id": order_id,
        })
        await update.message.reply_text(
            f"✅ Заказ успешно оформлен!\n"
            f"ID на BoostX5: {order_id}\n"
            f"Списано: {cost:.2f} ₽"
        )
    except Exception as e:
        set_balance(uid, bal)
        await update.message.reply_text(f"Ошибка создания заказа: {e}")

    context.user_data.pop("order", None)
    return ConversationHandler.END


async def order_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("order", None)
    await update.message.reply_text("Оформление отменено.")
    return ConversationHandler.END


from handlers.balance_pay import register_balance_handlers


def build_application():
    defaults = Defaults(parse_mode=ParseMode.HTML)
    app = ApplicationBuilder().token(BOT_TOKEN).defaults(defaults).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(CommandHandler("catalog", show_catalog))
    app.add_handler(CommandHandler("services", show_catalog))
    app.add_handler(CallbackQueryHandler(show_catalog, pattern="^catalog$"))
    app.add_handler(CallbackQueryHandler(show_category, pattern="^cat_"))

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(order_entry, pattern="^item_")],
        states={
            0: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_get_link)],
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_get_qty)],
        },
        fallbacks=[CommandHandler("cancel", order_cancel)],
        name="order_conv",
        persistent=False,
    )
    app.add_handler(conv)

    register_balance_handlers(app)
    return app


if __name__ == "__main__":
    application = build_application()
    print("Bot is running...")
    application.run_polling()
