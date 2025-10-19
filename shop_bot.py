import os
import json
import html
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN не задан. Добавь его в Render → Environment Variables.")

from handlers.menu import (
    show_catalog,
    view_product_cb,
    add_to_cart_cb,
    back_catalog_cb,
    show_cart,
    clear_cart_cb,
    checkout_cb,
    ask_note,
    ask_txn,
    finish_order,
    cancel_checkout,
    menu_kb,
)
from handlers.reply import register_reply_handler, reply_command
from handlers.balance_pay import register_balance_handlers

ASK_CONTACT, ASK_NOTE, ASK_TXN, ASK_QUESTION = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Добро пожаловать в BoostX!\n\nВыберите действие из меню ниже:",
        reply_markup=menu_kb(),
    )

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✏️ Напиши свой вопрос. Я передам его администратору.")
    return ASK_QUESTION

async def forward_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text
    user = update.effective_user
    text = f"📩 Вопрос от <b>{html.escape(user.full_name)}</b> (ID: {user.id}):\n\n{html.escape(question)}"
    if ADMIN_ID:
        await context.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="HTML")
    await update.message.reply_text("✅ Вопрос отправлен администратору.")
    return ConversationHandler.END

async def cancel_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

def build_application() -> Application:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^Каталог$"), show_catalog))
    app.add_handler(CallbackQueryHandler(view_product_cb, pattern=r"^view:"))
    app.add_handler(CallbackQueryHandler(add_to_cart_cb, pattern=r"^add:"))
    app.add_handler(CallbackQueryHandler(back_catalog_cb, pattern=r"^back:catalog$"))
    app.add_handler(MessageHandler(filters.Regex("^Корзина$"), show_cart))
    app.add_handler(CallbackQueryHandler(clear_cart_cb, pattern=r"^clear$"))

    checkout_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(checkout_cb, pattern=r"^checkout$")],
        states={
            ASK_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_note)],
            ASK_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_txn)],
            ASK_TXN: [
                MessageHandler(filters.Regex(r"^❌ Отменить оформление$"), cancel_checkout),
                MessageHandler(filters.TEXT & ~filters.COMMAND, finish_order),
            ],
        },
        fallbacks=[MessageHandler(filters.Regex(r"^❌ Отменить оформление$"), cancel_checkout)],
        allow_reentry=True,
    )
    app.add_handler(checkout_conv)

    ask_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📞 Задать вопрос$"), ask_question)],
        states={
            ASK_QUESTION: [
                MessageHandler(filters.Regex(r"^❌ Отменить оформление$"), cancel_question),
                MessageHandler(filters.TEXT & ~filters.COMMAND, forward_question),
            ],
        },
        fallbacks=[MessageHandler(filters.Regex(r"^❌ Отменить оформление$"), cancel_question)],
        allow_reentry=True,
    )
    app.add_handler(ask_conv)

    app.add_handler(
        MessageHandler(
            filters.Regex("^💬 Связаться с админом$"),
            lambda u, c: u.message.reply_text("📬 Напиши напрямую: @Delay34", reply_markup=menu_kb()),
        )
    )

    app.add_handler(CommandHandler("reply", reply_command))

    register_balance_handlers(app)

    return app

if __name__ == "__main__":
    application = build_application()
    print("✅ Bot is running on Render (BoostX)")
    application.run_polling()
