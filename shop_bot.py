import logging
import os
import uuid  # для генерации invoice_id
from typing import Dict, Any

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ================= НАСТРОЙКИ =================

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError(
        "Не найден BOT_TOKEN/TELEGRAM_TOKEN в переменных окружения. "
        "Добавь его в настройках Render."
    )

# ID админа / чата, куда будут уходить заявки и сообщения в поддержку
# Можно указать один и тот же ID
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
SUPPORT_CHAT_ID = os.getenv("SUPPORT_CHAT_ID") or ADMIN_CHAT_ID

# Ссылка для пополнения (PAY_URL из ENV)
PAY_URL = os.getenv("PAY_URL", "Ссылка для пополнения не настроена")

# Простая «база товаров» (можно потом заменить на свою)
PRODUCTS = {
    1: {
        "title": "Тестовый товар #1",
        "description": "Описание первого товара. Например: доступ к паку файлов.",
        "price": 199,  # в рублях (для текста, без реального платежного API)
    },
    2: {
        "title": "Тестовый товар #2",
        "description": "Описание второго товара. Можно заменить на любой.",
        "price": 349,
    },
}


# ================= ЛОГИРОВАНИЕ =================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ================= СОСТОЯНИЯ ДЛЯ CONVERSATIONHANDLER =================

ORDER_NAME, ORDER_CONTACT = range(2)
SUPPORT_MESSAGE = range(1)


# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================


def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📦 Товары", callback_data="menu_products")],
        [InlineKeyboardButton("✉ Поддержка", callback_data="menu_support")],
        [InlineKeyboardButton("ℹ О боте", callback_data="menu_info")],
    ]
    return InlineKeyboardMarkup(keyboard)


def products_keyboard() -> InlineKeyboardMarkup:
    keyboard = []
    for pid, item in PRODUCTS.items():
        keyboard.append(
            [InlineKeyboardButton(f"{item['title']} — {item['price']}₽", callback_data=f"product_{pid}")]
        )
    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def product_action_keyboard(product_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🛒 Оформить заказ", callback_data=f"buy_{product_id}")],
        [InlineKeyboardButton("⬅ Назад к товарам", callback_data="menu_products")],
    ]
    return InlineKeyboardMarkup(keyboard)


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_conv")]]
    )


def support_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_support")]]
    )


def get_user_tag(update: Update) -> str:
    user = update.effective_user
    if not user:
        return "Неизвестный пользователь"
    username = f"@{user.username}" if user.username else ""
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    if username and name:
        return f"{name} ({username}, id={user.id})"
    elif username:
        return f"{username} (id={user.id})"
    elif name:
        return f"{name} (id={user.id})"
    return f"id={user.id}"


def generate_invoice_id(update: Update) -> str:
    """Простая генерация invoice_id (можешь потом заменить своей логикой)."""
    user = update.effective_user
    base = str(user.id) if user else ""
    rand = uuid.uuid4().hex[:6].upper()
    return f"{base}-{rand}" if base else rand


# ================= ХЕНДЛЕРЫ КОМАНД =================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    invoice_id = generate_invoice_id(update)

    text = (
        "👋 Добро пожаловать в <b>BoostX</b> — платформу профессионального продвижения.\n\n"
        "Мы помогаем развивать <b>Telegram</b>, <b>YouTube</b> и <b>TikTok</b> "
        "с быстрыми и надёжными результатами.\n\n"
        "Откройте каталог, чтобы выбрать услугу, или воспользуйтесь кнопками ниже "
        "для управления балансом и связи с поддержкой.\n\n"
        "💳 <b>Пополнение баланса</b>\n\n"
        f"Ваш индивидуальный номер транзакции: <code>{invoice_id}</code>\n"
        "При переводе укажите этот номер в комментарии к платежу "
        "или в сообщении вместе с переводом, чтобы мы могли быстрее найти оплату.\n\n"
        "Ссылка для пополнения:\n"
        f"{PAY_URL}"
    )

    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML",
        )
    elif update.callback_query:
        await update.callback_query.message.edit_text(
            text,
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML",
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "❓ *Помощь*\n\n"
        "Основные команды:\n"
        "/start — главное меню\n"
        "/help — это сообщение\n\n"
        "Все заявки отправляются админу в личку/чат (настроено через переменные окружения)."
    )
    await update.message.reply_markdown(text)


# ================= ОБРАБОТКА CALLBACK-КНОПОК (МЕНЮ) =================


async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Роутер для простых callback_data меню."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "menu_main":
        await query.message.edit_text(
            "Главное меню 👇", reply_markup=main_menu_keyboard()
        )
        return

    if data == "menu_products":
        await query.message.edit_text(
            "📦 Список доступных товаров:", reply_markup=products_keyboard()
        )
        return

    if data == "menu_support":
        await query.message.edit_text(
            "✉ Напиши сообщение для поддержки.\n\n"
            "Опиши проблему или вопрос максимально подробно.\n\n"
            "Чтобы отменить, нажми кнопку ниже.",
            reply_markup=support_cancel_keyboard(),
        )
        return SUPPORT_MESSAGE

    if data == "menu_info":
        text = (
            "ℹ *О боте*\n\n"
            "Этот бот демонстрирует простую логику магазина в Telegram:\n"
            "— список товаров\n"
            "— оформление заявок\n"
            "— связь с поддержкой\n\n"
            "Логику можно легко расширить под любые задачи."
        )
        await query.message.edit_markdown(text, reply_markup=main_menu_keyboard())
        return

    # product_<id> — просмотр товара
    if data.startswith("product_"):
        try:
            pid = int(data.split("_", maxsplit=1)[1])
        except (ValueError, IndexError):
            await query.message.edit_text(
                "Ошибка: не получилось определить товар.",
                reply_markup=products_keyboard(),
            )
            return

        product = PRODUCTS.get(pid)
        if not product:
            await query.message.edit_text(
                "Такого товара больше нет.", reply_markup=products_keyboard()
            )
            return

        text = (
            f"*{product['title']}*\n\n"
            f"{product['description']}\n\n"
            f"Цена: *{product['price']}₽*"
        )
        await query.message.edit_markdown(
            text, reply_markup=product_action_keyboard(pid)
        )
        return


# ================= CONVERSATIONHANDLER: ОФОРМЛЕНИЕ ЗАКАЗА =================


async def order_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Старт оформления заказа по нажатию кнопки '🛒 Оформить заказ'."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("buy_"):
        await query.message.reply_text("Неизвестное действие.")
        return ConversationHandler.END

    try:
        product_id = int(data.split("_", maxsplit=1)[1])
    except (ValueError, IndexError):
        await query.message.reply_text("Ошибка: не удалось определить товар.")
        return ConversationHandler.END

    product = PRODUCTS.get(product_id)
    if not product:
        await query.message.reply_text("Такого товара больше нет.")
        return ConversationHandler.END

    context.user_data["order"] = {
        "product_id": product_id,
        "product_title": product["title"],
        "price": product["price"],
    }

    text = (
        f"🛒 *Оформление заказа*\n\n"
        f"Товар: *{product['title']}* ({product['price']}₽)\n\n"
        f"Для начала напиши *своё имя* (или как к тебе обращаться)."
    )

    await query.message.edit_markdown(text, reply_markup=cancel_keyboard())
    return ORDER_NAME


async def order_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text(
            "Пожалуйста, напиши имя текстом 🙏", reply_markup=cancel_keyboard()
        )
        return ORDER_NAME

    context.user_data.setdefault("order", {})
    context.user_data["order"]["name"] = name

    await update.message.reply_text(
        "Отлично! Теперь напиши удобный контакт для связи:\n"
        "• @username или\n"
        "• номер телефона или\n"
        "• любой другой удобный способ.",
        reply_markup=cancel_keyboard(),
    )
    return ORDER_CONTACT


async def order_get_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact = (update.message.text or "").strip()
    if not contact:
        await update.message.reply_text(
            "Пожалуйста, напиши контакт текстом 🙏", reply_markup=cancel_keyboard()
        )
        return ORDER_CONTACT

    order = context.user_data.get("order", {})
    order["contact"] = contact

    user_tag = get_user_tag(update)
    product_title = order.get("product_title", "Неизвестный товар")
    price = order.get("price", "—")
    name = order.get("name", "Не указано")

    admin_text = (
        "🆕 *Новая заявка*\n\n"
        f"Покупатель: {user_tag}\n"
        f"Имя: {name}\n"
        f"Контакт: {contact}\n\n"
        f"Товар: *{product_title}*\n"
        f"Цена: *{price}₽*\n"
    )

    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=int(ADMIN_CHAT_ID),
                text=admin_text,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error("Не удалось отправить заявку админу: %s", e)

    await update.message.reply_text(
        "Спасибо! 🙌\n\n"
        "Твоя заявка отправлена. В ближайшее время с тобой свяжется админ.\n\n"
        "Если что-то ещё понадобится — жми /start и выбирай пункт меню.",
        reply_markup=main_menu_keyboard(),
    )

    context.user_data.pop("order", None)
    return ConversationHandler.END


async def order_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "Оформление заказа отменено. Если передумаешь — просто выбери товар снова.",
        reply_markup=main_menu_keyboard(),
    )
    context.user_data.pop("order", None)
    return ConversationHandler.END


async def order_cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Оформление заказа отменено. Если передумаешь — просто выбери товар снова.",
        reply_markup=main_menu_keyboard(),
    )
    context.user_data.pop("order", None)
    return ConversationHandler.END


# ================= CONVERSATIONHANDLER: ПОДДЕРЖКА =================


async def support_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text(
            "Пожалуйста, отправь текстовое сообщение для поддержки 🙏",
            reply_markup=support_cancel_keyboard(),
        )
        return SUPPORT_MESSAGE

    user_tag = get_user_tag(update)

    admin_text = (
        "✉ *Сообщение в поддержку*\n\n"
        f"От: {user_tag}\n\n"
        f"Текст:\n{text}"
    )

    if SUPPORT_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=int(SUPPORT_CHAT_ID),
                text=admin_text,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error("Не удалось отправить сообщение в поддержку: %s", e)

    await update.message.reply_text(
        "Спасибо! Твоё сообщение отправлено в поддержку. "
        "Ответ придёт в ближайшее время.",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


async def support_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "Обращение в поддержку отменено.", reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END


# ================= MAIN =================


def build_application() -> Any:
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_order = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(order_entry, pattern=r"^buy_\d+$"),
        ],
        states={
            ORDER_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_get_name)
            ],
            ORDER_CONTACT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_get_contact)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", order_cancel_cmd),
            CallbackQueryHandler(order_cancel_cb, pattern=r"^cancel_conv$"),
        ],
        per_message=True,
    )

    conv_support = ConversationHandler(
        entry_points=[],
        states={
            SUPPORT_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support_message)
            ],
        },
        fallbacks=[
            CallbackQueryHandler(support_cancel_cb, pattern=r"^cancel_support$"),
        ],
        per_message=True,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(
        CallbackQueryHandler(
            menu_router,
            pattern=r"^(menu_main|menu_products|menu_support|menu_info|product_\d+)$",
        )
    )

    application.add_handler(CallbackQueryHandler(support_cancel_cb, pattern=r"^cancel_support$"))

    application.add_handler(conv_order)
    application.add_handler(conv_support)

    return application


def main() -> None:
    application = build_application()

    render_url = os.getenv("RENDER_EXTERNAL_URL")
    port = int(os.getenv("PORT", "8000"))

    if render_url:
        webhook_url = f"{render_url}/{BOT_TOKEN}"
        logger.info(f"Запуск в режиме WEBHOOK: {webhook_url} (порт {port})")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=BOT_TOKEN,
            webhook_url=webhook_url,
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        logger.info("Запуск в режиме POLLING")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
