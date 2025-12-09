# -*- coding: utf-8 -*-
import json
import logging
import os
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
    Defaults,
)
from telegram.constants import ParseMode

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PAY_URL = os.getenv("PAY_URL", "")

# Настройки вебхука для Render
PORT = int(os.getenv("PORT", "10000"))
# Можно явно задать WEBHOOK_URL в переменных окружения,
# например: https://your-service.onrender.com/<BOT_TOKEN>
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# ================================
#         ЗАГРУЗКА КАТАЛОГА
# ================================
def load_catalog():
    try:
        with open("config/config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"categories": []}


# ================================
#      КОМАНДА /START
# ================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Добро пожаловать в <b>BoostX</b> — платформу профессионального продвижения.\n\n"
        "Мы помогаем развивать <b>Telegram</b>, <b>YouTube</b> и <b>TikTok</b> "
        "с быстрыми и надёжными результатами.\n\n"
        "Откройте каталог, чтобы выбрать услугу, или воспользуйтесь кнопками ниже "
        "для управления балансом и связи с поддержкой."
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Каталог", callback_data="catalog")],
        [
            InlineKeyboardButton("💳 Баланс", callback_data="balance"),
            InlineKeyboardButton("💳 Пополнить", callback_data="topup"),
        ],
        [InlineKeyboardButton("🆘 Поддержка", callback_data="support")],
    ])

    if update.message:
        await update.message.reply_html(text, reply_markup=kb)
    elif update.callback_query:
        await update.callback_query.message.reply_html(text, reply_markup=kb)


# ================================
#         ПОКАЗ КАТЕГОРИЙ
# ================================
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
        [InlineKeyboardButton(cat.get("title", "Категория"), callback_data=f"cat_{i}")]
        for i, cat in enumerate(cats)
    ]

    kb = InlineKeyboardMarkup(buttons)
    target = query.message if query else update.message
    await target.reply_html(
        "<b>📋 Каталог BoostX</b>\n\nВыберите категорию:",
        reply_markup=kb,
    )


# ================================
#     ОТКРЫТИЕ КОНКРЕТНОЙ КАТЕГОРИИ
# ================================
async def show_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    cat_id = int(q.data.split("_")[1])
    data = load_catalog()
    category = data["categories"][cat_id]

    buttons = [
        [
            InlineKeyboardButton(
                item["title"], callback_data=f"item_{cat_id}_{i}"
            )
        ]
        for i, item in enumerate(category["items"])
    ]

    kb = InlineKeyboardMarkup(buttons)
    await q.message.edit_html(
        f"<b>{category['title']}</b>\nВыберите услугу:", reply_markup=kb
    )


# ================================
#      ОФОРМЛЕНИЕ ЗАКАЗА
# ================================
LINK, QTY = range(2)


async def order_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    _, cat_id, item_id = q.data.split("_")
    cat_id = int(cat_id)
    item_id = int(item_id)

    context.user_data["order"] = {"cat_id": cat_id, "item_id": item_id}

    await q.message.reply_text("Отправьте ссылку для накрутки:")
    return LINK


async def order_get_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order"]["link"] = update.message.text
    await update.message.reply_text("Введите количество:")
    return QTY


async def order_get_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qty = update.message.text
    order = context.user_data["order"]

    await update.message.reply_text(
        f"Ваш заказ оформлен!\n\n"
        f"Категория ID: {order['cat_id']}\n"
        f"Услуга ID: {order['item_id']}\n"
        f"Ссылка: {order['link']}\n"
        f"Количество: {qty}"
    )

    return ConversationHandler.END


async def order_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Оформление заказа отменено.")
    return ConversationHandler.END


# ================================
#         БАЛАНС
# ================================
async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ваш баланс: 0₽")


async def balance_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("Ваш баланс: 0₽")


# ================================
#        ПОПОЛНЕНИЕ
# ================================
async def topup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ссылка на оплату: {PAY_URL}")


async def topup_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_html(f"Ссылка для пополнения:\n\n<code>{PAY_URL}</code>")


# ================================
#         ПОДДЕРЖКА
# ================================
SUPPORT = range(1)


async def support_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("Напишите ваш вопрос одним сообщением:")
    return SUPPORT


async def support_collect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    msg = (
        f"🆘 Обращение в поддержку\n\n"
        f"От: {user.full_name} (@{user.username})\n"
        f"ID: {user.id}\n\n"
        f"Сообщение:\n{text}"
    )

    if ADMIN_ID:
        await context.bot.send_message(ADMIN_ID, msg)

    await update.message.reply_text("Ваше сообщение отправлено. Ожидайте ответа.")
    return ConversationHandler.END


async def support_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Диалог отменён.")
    return ConversationHandler.END


# ================================
#      КОМАНДА /REPLY ДЛЯ АДМИНА
# ================================
async def reply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("Команда доступна только администратору!")

    if len(context.args) < 2:
        return await update.message.reply_text("Использование: /reply <user_id> <текст>")

    user_id = int(context.args[0])
    text = " ".join(context.args[1:])

    await context.bot.send_message(user_id, text)
    await update.message.reply_text("Ответ отправлен.")


# ================================
#         СБОРКА ПРИЛОЖЕНИЯ
# ================================
def build_application():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .defaults(Defaults(parse_mode=ParseMode.HTML))
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reply", reply_cmd))

    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CallbackQueryHandler(balance_cb, pattern="^balance$"))

    app.add_handler(CommandHandler("topup", topup_cmd))
    app.add_handler(CallbackQueryHandler(topup_cb, pattern="^topup$"))

    app.add_handler(CallbackQueryHandler(show_catalog, pattern="^catalog$"))
    app.add_handler(CommandHandler("catalog", show_catalog))

    app.add_handler(CallbackQueryHandler(show_category, pattern="^cat_"))

    conv_order = ConversationHandler(
        entry_points=[CallbackQueryHandler(order_entry, pattern="^item_")],
        states={
            LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_get_link)],
            QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_get_qty)],
        },
        fallbacks=[CommandHandler("cancel", order_cancel)],
    )
    app.add_handler(conv_order)

    conv_support = ConversationHandler(
        entry_points=[CallbackQueryHandler(support_entry, pattern="^support$")],
        states={SUPPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_collect)]},
        fallbacks=[CommandHandler("cancel", support_cancel)],
    )
    app.add_handler(conv_support)

    return app


if __name__ == "__main__":
    application = build_application()

    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set")

    if not WEBHOOK_URL:
        raise SystemExit("WEBHOOK_URL (или RENDER_EXTERNAL_URL) не задан")

    # Полный URL для вебхука: WEBHOOK_URL + '/' + BOT_TOKEN
    webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    print(f"🚀 Starting BoostX bot via webhook on port {PORT}...")
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=webhook_url,
        drop_pending_updates=True,
    )
