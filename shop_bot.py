# -*- coding: utf-8 -*-
"""
Telegram Shop Bot — premium edition (python-telegram-bot 21.x)

Функции:
• Красивое приветствие /start и аккуратные сообщения (HTML)
• Меню: Каталог / Корзина / 📞 Задать вопрос / 💬 Связаться с админом
• Каталог услуг → добавление в корзину
• Оформление заказа: авто‑подстановка @username (если есть), реквизиты карты, ввод номера транзакции
• Сохранение заказов в orders.json
• «Задать вопрос» с мостом: админ может ответить пользователю через /reply <user_id> <текст>
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Dict, List, Tuple

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ─────────────────────────────────────────────────────────────────────────────
# Конфиг (.env)
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CARD_DETAILS = os.getenv("CARD_DETAILS", "Т-Банк: 0000 0000 0000 0000 — Имя Фамилия")
PAY_INSTRUCTIONS = os.getenv("PAY_INSTRUCTIONS", "Переведите точную сумму на карту и пришлите номер транзакции/чека.")
ORDERS_FILE = Path(os.getenv("ORDERS_FILE", "orders.json"))

# ─────────────────────────────────────────────────────────────────────────────
# Данные магазина
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Product:
    id: str
    title: str
    price: int  # рубли
    description: str

PRODUCTS: Dict[str, Product] = {
    "BASIC": Product(
        id="BASIC",
        title='💎 Пакет "БАЗОВЫЙ СТАРТ"',
        price=1500,
        description=(
            "💙 Аудит контента и визуала\n"
            "💙 Рекомендации по стратегии роста\n"
            "💙 Анализ 3 конкурентов\n"
            "💙 Гайд по улучшению вовлеченности"
        ),
    ),
    "STRATEGY": Product(
        id="STRATEGY",
        title='💎 Пакет "СТРАТЕГИЧЕСКИЙ РЫВОК"',
        price=3000,
        description=(
            "💙 Полный аудит всех площадок\n"
            "💙 Контент-стратегия на 2 недели\n"
            "💙 Настройка автопостинга\n"
            "💙 Рекомендации по монетизации"
        ),
    ),
    "UPGRADE": Product(
        id="UPGRADE",
        title='💎 Пакет "КОМПЛЕКСНЫЙ АПГРЕЙД"',
        price=5000,
        description=(
            "💙 Ребрендинг визуала (обложки, шаблоны)\n"
            "💙 Единая стратегия для 2 платформ\n"
            "💙 Настройка Telegram Ads\n"
            "💙 Еженедельная аналитика и поддержка"
        ),
    ),
    "TG_DESIGN": Product(
        id="TG_DESIGN",
        title="🎨 Оформление вашего Telegram канала",
        price=500,
        description=(
            "Придайте вашему каналу профессиональный вид\n\n"
            "• Уникальный визуальный стиль\n"
            "• Шапка профиля, шаблоны постов/сторис\n"
            "• Подбор палитры и шрифтов\n"
            "• Повышение узнаваемости бренда"
        ),
    ),
    "VK_DESIGN": Product(
        id="VK_DESIGN",
        title="🔥 Оформление вашей группы VKонтакте",
        price=500,
        description=(
            "Прокачаем сообщество ВК для привлечения клиентов\n\n"
            "• Дизайн шапки и меню\n"
            "• Обложки для товаров/обсуждений\n"
            "• Шаблоны постов\n"
            "• Оптимизация под ЦА"
        ),
    ),
    "FULL_MANAGEMENT": Product(
        id="FULL_MANAGEMENT",
        title="🚀 Полное ведение вашего проекта",
        price=6500,
        description=(
            "Комплекс для роста в соцсетях\n\n"
            "• Стратегия на 2 недели\n"
            "• Ежедневный контент и публикация\n"
            "• Мониторинг и ответы\n"
            "• Аналитика и корректировки"
        ),
    ),
    "TG_AUDIT": Product(
        id="TG_AUDIT",
        title="📊 Аудит вашего канала Telegram",
        price=350,
        description=(
            "Выявим слабые места и точки роста\n\n"
            "• Анализ контента и визуала\n"
            "• Исследование аудитории и конкурентов\n"
            "• Рекомендации по вовлеченности\n"
            "• План из 10 шагов"
        ),
    ),
    "WEEKLY_PLAN": Product(
        id="WEEKLY_PLAN",
        title="📅 Контент-план на неделю",
        price=400,
        description=(
            "Готовая стратегия на 7 дней\n\n"
            "• 7 идей постов\n"
            "• Время публикаций\n"
            "• Форматы под вашу ЦА\n"
            "• Советы по визуалу и сторис"
        ),
    ),
}

# Корзины в памяти процесса: user_id -> {product_id: qty}
CART: Dict[int, Dict[str, int]] = {}
CART_LOCK = Lock()

# Состояния диалогов
ASK_CONTACT, ASK_NOTE, ASK_TXN = range(3)
ASK_QUESTION = range(1)  # для «Задать вопрос»

# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные элементы UI
# ─────────────────────────────────────────────────────────────────────────────
DIV = "─" * 42

def menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["Каталог", "Корзина"],
            ["📞 Задать вопрос", "💬 Связаться с админом"],
        ],
        resize_keyboard=True,
    )

def catalog_ikb() -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for p in PRODUCTS.values():
        rows.append([InlineKeyboardButton(f"{p.title} — {p.price}₽", callback_data=f"view:{p.id}")])
    return InlineKeyboardMarkup(rows)

def product_ikb(pid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ В корзину", callback_data=f"add:{pid}")],
            [InlineKeyboardButton("⬅️ Назад к каталогу", callback_data="back:catalog")],
        ]
    )

def cart_ikb(has_items: bool) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    if has_items:
        rows.append([InlineKeyboardButton("✅ Оформить заказ", callback_data="checkout")])
        rows.append([InlineKeyboardButton("🧹 Очистить корзину", callback_data="clear")])
    rows.append([InlineKeyboardButton("⬅️ К каталогу", callback_data="back:catalog")])
    return InlineKeyboardMarkup(rows)

# ─────────────────────────────────────────────────────────────────────────────
# Утилиты
# ─────────────────────────────────────────────────────────────────────────────
def get_cart(user_id: int) -> Dict[str, int]:
    with CART_LOCK:
        return CART.setdefault(user_id, {})

def cart_summary(user_id: int) -> Tuple[str, int]:
    items = get_cart(user_id)
    if not items:
        return "Ваша корзина пуста.", 0
    lines = [f"<b>🧺 Корзина</b>\n{DIV}"]
    total = 0
    for pid, qty in items.items():
        p = PRODUCTS.get(pid)
        if not p:
            continue
        s = p.price * qty
        total += s
        lines.append(f"• {p.title} × {qty} = <b>{s}₽</b>")
    lines.append(f"{DIV}\n<b>Итого: {total}₽</b>")
    return "\n".join(lines), total

def append_order(order: dict) -> None:
    data = []
    if ORDERS_FILE.exists():
        try:
            data = json.loads(ORDERS_FILE.read_text("utf-8"))
        except Exception:
            data = []
    data.append(order)
    ORDERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def user_mention(u) -> str:
    if getattr(u, "username", None):
        return f"@{u.username}"
    name = f"{u.first_name or ''} {u.last_name or ''}".strip()
    return name or f"id:{u.id}"

# ─────────────────────────────────────────────────────────────────────────────
# Хендлеры
# ─────────────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    greeting = (
        "💎 <b>Привет!</b> Я — твой цифровой помощник по SMM и дизайну.\n\n"
        "Здесь ты можешь заказать профессиональное оформление и продвижение твоих проектов "
        "в Telegram, VK и другие площадки!\n\n"
        f"{DIV}\n"
        "<b>Что ты можешь сделать:</b>\n"
        "🛍️ Посмотреть каталог — выбрать и заказать нужную услугу\n"
        "📞 Задать вопрос — получить консультацию перед заказом\n"
        "📝 Оформить заказ — легко и быстро, в несколько кликов\n\n"
        "Готов усилить твой проект? Нажми «Каталог»! 👇"
    )
    await update.message.reply_text(greeting, parse_mode=ParseMode.HTML, reply_markup=menu_kb())

# — Каталог
async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    header = f"<b>Каталог услуг</b>\n{DIV}\nВыберите услугу ниже:"
    if update.message:
        await update.message.reply_text(header, parse_mode=ParseMode.HTML, reply_markup=menu_kb())
        await update.message.reply_text("▼", reply_markup=catalog_ikb())
    else:
        q = update.callback_query
        await q.message.edit_text(header, parse_mode=ParseMode.HTML, reply_markup=catalog_ikb())
        await q.answer()

async def view_product_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    pid = q.data.split(":", 1)[1]
    p = PRODUCTS.get(pid)
    if not p:
        await q.answer("Услуга не найдена", show_alert=True)
        return
    text = f"<b>{p.title}</b>\n{DIV}\n{p.description}\n\nЦена: <b>{p.price}₽</b>"
    await q.message.edit_text(text, reply_markup=product_ikb(p.id), parse_mode=ParseMode.HTML)
    await q.answer()

async def add_to_cart_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    pid = q.data.split(":", 1)[1]
    if pid not in PRODUCTS:
        await q.answer("Услуга не найдена", show_alert=True)
        return
    items = get_cart(q.from_user.id)
    items[pid] = items.get(pid, 0) + 1
    await q.answer("Добавлено в корзину")
    text, _ = cart_summary(q.from_user.id)
    await q.message.edit_text(text, reply_markup=cart_ikb(True), parse_mode=ParseMode.HTML)

async def back_catalog_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_catalog(update, context)

# — Корзина
async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.message.from_user.id
    text, _ = cart_summary(uid)
    await update.message.reply_text(text, reply_markup=cart_ikb(bool(get_cart(uid))), parse_mode=ParseMode.HTML)

async def clear_cart_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    with CART_LOCK:
        CART[q.from_user.id] = {}
    await q.answer("Корзина очищена")
    text, _ = cart_summary(q.from_user.id)
    await q.message.edit_text(text, reply_markup=cart_ikb(False), parse_mode=ParseMode.HTML)

# — Оформление заказа с авто-username
async def checkout_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    items = get_cart(q.from_user.id)
    if not items:
        await q.answer("Корзина пуста", show_alert=True)
        return ConversationHandler.END

    user = q.from_user
    username = f"@{user.username}" if user.username else None
    if username:
        context.user_data["contact"] = username
        await q.message.edit_text(
            f"<b>Оформление заказа</b>\n{DIV}\nВаш username: {username}\n\n"
            "Теперь напишите комментарий/пожелания или другой способ связи (по желанию).",
            parse_mode=ParseMode.HTML
        )
        return ASK_NOTE
    else:
        await q.message.edit_text(
            f"<b>Оформление заказа</b>\n{DIV}\nУ вас нет публичного @username.\n"
            "Пожалуйста, напишите, как с вами связаться (телеграм-ник или телефон).",
            parse_mode=ParseMode.HTML
        )
        return ASK_CONTACT

async def ask_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if "contact" not in context.user_data:
        context.user_data["contact"] = update.message.text.strip()
        await update.message.reply_text("Спасибо! Теперь укажите комментарий к заказу (по желанию).")
        return ASK_NOTE

    context.user_data["note"] = update.message.text.strip()
    text = (
        f"<b>Оплата реквизитами</b>\n{DIV}\n\n"
        f"Карта: <code>{CARD_DETAILS}</code>\n\n"
        f"{PAY_INSTRUCTIONS}\n\n"
        "После оплаты пришлите сюда <b>номер транзакции/чека</b> одним сообщением."
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("❌ Отменить оформление")]], resize_keyboard=True, one_time_keyboard=True
        ),
    )
    return ASK_TXN

async def ask_txn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["note"] = update.message.text.strip()
    text = (
        f"<b>Оплата реквизитами</b>\n{DIV}\n\n"
        f"Карта: <code>{CARD_DETAILS}</code>\n\n"
        f"{PAY_INSTRUCTIONS}\n\n"
        "После оплаты пришлите сюда <b>номер транзакции/чека</b> одним сообщением."
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("❌ Отменить оформление")]], resize_keyboard=True, one_time_keyboard=True
        ),
    )
    return ASK_TXN

async def finish_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    uid = user.id
    txn = update.message.text.strip()

    items = get_cart(uid)
    _, total = cart_summary(uid)

    order = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_id": uid,
        "user": {"username": user.username, "first_name": user.first_name, "last_name": user.last_name},
        "items": [
            {"id": pid, "title": PRODUCTS[pid].title, "qty": qty, "price": PRODUCTS[pid].price}
            for pid, qty in items.items()
        ],
        "total": total,
        "contact": context.user_data.get("contact"),
        "note": context.user_data.get("note"),
        "transaction": txn,
    }

    append_order(order)

    if ADMIN_ID:
        cart_lines = "\n".join(
            f"• {PRODUCTS[pid].title} × {qty} = {PRODUCTS[pid].price * qty}₽" for pid, qty in items.items()
        )
        admin_text = (
            f"🧾 <b>Новый заказ</b>\n{DIV}\n"
            f"Покупатель: {user_mention(user)} (id {uid})\n"
            f"Контакт: {order['contact']}\n"
            f"Комментарий: {order['note']}\n\n"
            f"{cart_lines}\n\n"
            f"<b>Итого: {total}₽</b>\n"
            f"Транзакция/чек: <code>{txn}</code>"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode=ParseMode.HTML)
        except Exception:
            pass

    with CART_LOCK:
        CART[uid] = {}

    await update.message.reply_text(
        "Спасибо! Заказ оформлен. Мы свяжемся с вами в ближайшее время.",
        reply_markup=menu_kb(),
    )
    return ConversationHandler.END

async def cancel_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Оформление отменено.", reply_markup=menu_kb())
    return ConversationHandler.END

# — «Задать вопрос» с мостом для ответа админа
USER_QUESTIONS: Dict[int, int] = {}  # user_id -> last_admin_message_id

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "✏️ Напиши свой вопрос — передам специалисту. Ответ придёт сюда.",
        reply_markup=ReplyKeyboardMarkup([["❌ Отменить оформление"]], resize_keyboard=True, one_time_keyboard=True),
    )
    return ASK_QUESTION

async def forward_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    text = update.message.text.strip()
    admin_text = (
        f"📩 <b>Новый вопрос</b>\n{DIV}\n"
        f"От: {user_mention(user)} (id {user.id})\n\n"
        f"<b>Текст:</b>\n{text}\n\n"
        f"✏️ Чтобы ответить — пришлите:\n"
        f"/reply {user.id} ваш_текст"
    )
    msg = None
    if ADMIN_ID:
        try:
            msg = await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode=ParseMode.HTML)
        except Exception:
            pass

    if msg:
        USER_QUESTIONS[user.id] = msg.message_id

    await update.message.reply_text("✅ Вопрос передан. Ответ придёт сюда.", reply_markup=menu_kb())
    return ConversationHandler.END

async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_ID:
        return  # только админ
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /reply user_id текст")
        return
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Неверный user_id.")
        return
    reply_text = " ".join(context.args[1:]).strip()
    if not reply_text:
        await update.message.reply_text("Пустой ответ.")
        return
    try:
        await context.bot.send_message(chat_id=user_id, text=f"💬 Ответ администратора:\n\n{reply_text}")
        await update.message.reply_text("✅ Сообщение отправлено пользователю.")
    except Exception as e:
        await update.message.reply_text(f"Не удалось отправить: {e}")

async def cancel_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Отменено.", reply_markup=menu_kb())
    return ConversationHandler.END

# ─────────────────────────────────────────────────────────────────────────────
# Приложение
# ─────────────────────────────────────────────────────────────────────────────


    # 🔗 BoostX: регистрация баланса/оплат и поставщика
    register_balance_handlers(app)\2


if __name__ == "__main__":
    application = build_application()
    print("Bot is running...")
    application.run_polling()
