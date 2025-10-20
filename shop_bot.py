# -*- coding: utf-8 -*-
"""
BoostX Telegram Bot — версия с балансом, ручной оплатой и интеграцией LookSMM.
Готово для деплоя на Render (python shop_bot.py).
"""

from __future__ import annotations
import os, json
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    Defaults,
)
from telegram.constants import ParseMode

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ORDERS_FILE = os.getenv("ORDERS_FILE", "orders.json")
PAY_INSTRUCTIONS = os.getenv(
    "PAY_INSTRUCTIONS",
    "Переведите точную сумму на карту и отправьте номер транзакции в ответ.",
)

def load_products():
    path = Path("config/config.json")
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        products = []
        for category in data.get("categories", []):
            for item in category.get("items", []):
                name = item.get("title") or item.get("name") or "—"
                price = item.get("price", "—")
                products.append({"name": name, "price": price})
        return products
    except Exception as e:
        print("Ошибка загрузки каталога:", e)
        return []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Добро пожаловать в <b>BoostX</b>!\n\n"
        "Нажмите «Каталог», чтобы выбрать услугу.\n"
        "Используйте /balance для проверки баланса или /topup для пополнения."
    )
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 Каталог", callback_data="catalog")],
            [InlineKeyboardButton("💳 Баланс", callback_data="balance")],
        ]
    )
    if update.message:
        await update.message.reply_html(text, reply_markup=kb)
    elif update.callback_query:
        await update.callback_query.message.reply_html(text, reply_markup=kb)

async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = load_products()
    if not products:
        await update.callback_query.message.reply_text("Каталог временно пуст.")
        return

    msg = "<b>Каталог услуг</b>\n\nВыберите услугу ниже:\n"
    for p in products:
        name = p.get("name", "—")
        price = p.get("price", "—")
        msg += f"💎 {name} — <b>{price}₽</b>\n"
    await update.callback_query.message.reply_html(msg)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 Команды:\n"
        "/start — приветствие\n"
        "/catalog — каталог услуг (кнопка «Каталог»)\n"
        "/balance — баланс\n"
        "/topup &lt;сумма&gt; — пополнить баланс\n"
        "/services — список услуг LookSMM\n"
        "/buy &lt;id&gt; &lt;ссылка&gt; &lt;кол-во&gt; — заказать услугу у поставщика\n"
        "/confirm_payment &lt;invoice_id&gt; — подтверждение оплаты (админ)\n"
    )

from handlers.balance_pay import register_balance_handlers

def build_application():
    defaults = Defaults(parse_mode=ParseMode.HTML)
    app = ApplicationBuilder().token(BOT_TOKEN).defaults(defaults).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(show_catalog, pattern="^catalog$"))
    register_balance_handlers(app)
    return app

if __name__ == "__main__":
    application = build_application()
    print("Bot is running...")
    application.run_polling()
