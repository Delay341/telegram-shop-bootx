# -*- coding: utf-8 -*-
"""
BoostX Telegram Bot — версия с балансом, ручной оплатой и интеграцией LookSMM
Работает на python-telegram-bot 21.x (и старше)
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
    Defaults,   # ✅ добавлено
)
from telegram.constants import ParseMode

# ─────────────────────────────────────────────────────────
# ENV
# ─────────────────────────────────────────────────────────
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ORDERS_FILE = os.getenv("ORDERS_FILE", "orders.json")
PAY_INSTRUCTIONS = os.getenv(
    "PAY_INSTRUCTIONS",
    "Переведите точную сумму на карту и отправьте номер транзакции в ответ.",
)

# ─────────────────────────────────────────────────────────
# JSON utils
# ─────────────────────────────────────────────────────────
def load_json(path: str | Path, default):
    try:
        p = Path(path)
        if not p.exists():
            return default
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


# ─────────────────────────────────────────────────────────
# Handlers (basic)
# ─────────────────────────────────────────────────────────
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
    await update.message.reply_html(text, reply_markup=kb)


async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = load_json("config/products.json", [])
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
        "/topup <сумма> — пополнить баланс\n"
        "/services — список услуг LookSMM\n"
        "/buy <id> <ссылка> <кол-во> — заказать услугу у поставщика\n"
        "/confirm_payment <invoice_id> — подтверждение оплаты (админ)\n"
    )


# ─────────────────────────────────────────────────────────
# Balance + LookSMM
# ─────────────────────────────────────────────────────────
from handlers.balance_pay import register_balance_handlers


# ─────────────────────────────────────────────────────────
# App builder
# ─────────────────────────────────────────────────────────
def build_application():
    # ✅ корректная версия с Defaults(parse_mode=HTML)
    defaults = Defaults(parse_mode=ParseMode.HTML)
    app = ApplicationBuilder().token(BOT_TOKEN).defaults(defaults).build()

    # базовые команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(show_catalog, pattern="^catalog$"))

    # баланс/оплата/LookSMM
    register_balance_handlers(app)

    return app


# ─────────────────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    application = build_application()
    print("Bot is running...")
    application.run_polling()
