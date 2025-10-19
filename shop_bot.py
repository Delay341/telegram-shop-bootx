# ─────────────────────────────────────────────────────────────────────────────
# Приложение (исправленный хвост файла shop_bot.py)
# ─────────────────────────────────────────────────────────────────────────────
def build_application():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Регистрация хендлеров
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^Каталог$"), show_catalog))
    app.add_handler(CallbackQueryHandler(view_product_cb, pattern=r"^view:"))
    app.add_handler(CallbackQueryHandler(add_to_cart_cb, pattern=r"^add:"))
    app.add_handler(CallbackQueryHandler(back_catalog_cb, pattern=r"^back:catalog$"))
    app.add_handler(MessageHandler(filters.Regex("^Корзина$"), show_cart))
    app.add_handler(CallbackQueryHandler(clear_cart_cb, pattern=r"^clear$"))

    # Оформление заказа
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

    # Диалог «Задать вопрос»
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

    # Кнопка «Связаться с админом»
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^💬 Связаться с админом$"),
            lambda u, c: u.message.reply_text("📬 Напиши напрямую: @Delay34", reply_markup=menu_kb()),
        )
    )

    # Команда для ответа админа
    app.add_handler(CommandHandler("reply", reply_command))

    # Подключаем систему баланса и оплат
    from handlers.balance_pay import register_balance_handlers
    register_balance_handlers(app)

    return app


if __name__ == "__main__":
    application = build_application()
    print("Bot is running...")
    application.run_polling()