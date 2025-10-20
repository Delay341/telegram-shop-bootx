# -*- coding: utf-8 -*-
"""
BoostX Telegram Bot — версия с балансом, ручной оплатой и интеграцией LookSMM
Готов для Render как worker (или web) со стартом: python shop_bot.py
"""

from __future__ import annotations
import os
import json
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    Defaults,
)

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
# Catalog loader (config/config.json)
# Ожидаемый формат:
# {
#   "categories":[
#     {"name":"...", "items":[{"title":"...", "price":123}, ...]},
#     ...
#   ]
# }
# ─────────────────────────────────────────────────────────
CATALOG_PATH = Path("config/config.json")
MAX_CHUNK = 4000  # лимит телеги ~4096, оставим запас

def load_products():
    if not CATALOG_PATH.exists():
        return []
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        products = []
        for category in data.get("categories", []):
            for item in category.get("items", []):
                name = item.get("title") or item.get("name") or "—"
                price = item.get("price", "—")
                products.append({"name": str(name), "price": str(price)})
        return products
    except Exception as e:
        print("Ошибка загрузки каталога:", e)
        return []

def chunk_text_html(text: str, max_len: int = MAX_CHUNK):
    out = []
    while text:
        chunk = text[:max_len]
        cut = chunk.rfind("\n")
        if 1000 < cut < max_len:
            chunk = chunk[:cut]
        out.append(chunk)
        text = text[len(chunk):].lstrip()
    return out

async def send_catalog(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    products = load_products()
    if not products:
        await context.bot.send_message(chat_id, "Каталог временно пуст.")
        return
    header = "<b>Каталог услуг</b>\n\nВыберите услугу ниже:\n"
    lines = [f"💎 {p['name']} — <b>{p['price']}₽</b>" for p in products]
    full = header + "\n".join(lines)
    for part in chunk_text_html(full):
        await context.bot.send_message(chat_id, part, parse_mode=ParseMode.HTML)

# ─────────────────────────────────────────────────────────
# Basic handlers
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
    if update.message:
        await update.message.reply_html(text, reply_markup=kb)
    elif update.callback_query:
        await update.callback_query.message.reply_html(text, reply_markup=kb)

async def catalog_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_catalog(update.effective_chat.id, context)

async def catalog_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_catalog(update.effective_chat.id, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 Команды:\n"
        "/start — приветствие\n"
        "/catalog — каталог услуг (или кнопка «Каталог»)\n"
        "/balance — баланс\n"
        "/topup &lt;сумма&gt; — пополнить баланс\n"
        "/services — список услуг LookSMM\n"
        "/buy &lt;id&gt; &lt;ссылка&gt; &lt;кол-во&gt; — заказать услугу у поставщика\n"
        "/confirm_payment &lt;invoice_id&gt; — подтверждение оплаты (админ)\n"
        "/ping — проверка ответа бота\n"
        "/debug — сведения о сборке/каталоге\n"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        from telegram.ext import __version__ as ptb_ver
    except Exception:
        ptb_ver = "unknown"
    ok_token = bool(BOT_TOKEN and len(BOT_TOKEN) > 20)
    exists_catalog = CATALOG_PATH.exists()
    await update.message.reply_text(
        "🤖 Debug:\n"
        f"PTB: {ptb_ver}\n"
        f"Token set: {ok_token}\n"
        f"Products file: {'exists' if exists_catalog else 'missing'}\n"
        f"Products count: {len(load_products()) if exists_catalog else 0}"
    )

# ─────────────────────────────────────────────────────────
# Balance + LookSMM
# ─────────────────────────────────────────────────────────
from handlers.balance_pay import register_balance_handlers

# ─────────────────────────────────────────────────────────
# App builder
# ─────────────────────────────────────────────────────────
def build_application():
    defaults = Defaults(parse_mode=ParseMode.HTML)
    app = ApplicationBuilder().token(BOT_TOKEN).defaults(defaults).build()

    # базовые команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("catalog", catalog_cmd))
    app.add_handler(CallbackQueryHandler(catalog_btn, pattern="^catalog$"))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("debug", debug))

    # баланс / оплаты / LookSMM
    register_balance_handlers(app)

    return app

# ─────────────────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    application = build_application()
    print("Bot is running...")
    application.run_polling()
