
# -*- coding: utf-8 -*-
import os
import json
import html
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from pathlib import Path
from typing import Dict, List, Tuple

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CARD_DETAILS = os.getenv("CARD_DETAILS", "https://www.tinkoff.ru/rm/r_nIutIhQtbX.tRouMxMcdC/kgUL962390")
PAY_INSTRUCTIONS = os.getenv("PAY_INSTRUCTIONS", "В сообщение к переведу укажите: Ваш @username, услугу, количество")
ORDERS_FILE = Path(os.getenv("ORDERS_FILE", "orders.json"))

if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN не задан. Добавь его в Render → Environment Variables.")

# ——— Каталог
@dataclass(frozen=True)
class Product:
    id: str
    title: str
    price: int
    description: str

PRODUCTS: Dict[str, Product] = {
    "BASIC": Product("BASIC", '💎 Пакет "БАЗОВЫЙ СТАРТ"', 1500,
        "💙 Аудит контента и визуала\n💙 Рекомендации по стратегии роста\n💙 Анализ 3 конкурентов\n💙 Гайд по улучшению вовлеченности"),
    "STRATEGY": Product("STRATEGY", '💎 Пакет "СТРАТЕГИЧЕСКИЙ РЫВОК"', 3000,
        "💙 Полный аудит всех площадок\n💙 Контент-стратегия на 2 недели\n💙 Настройка автопостинга\n💙 Рекомендации по монетизации"),
    "UPGRADE": Product("UPGRADE", '💎 Пакет "КОМПЛЕКСНЫЙ АПГРЕЙД"', 5000,
        "💙 Ребрендинг визуала (обложки, шаблоны)\n💙 Единая стратегия для 2 платформ\n💙 Настройка Telegram Ads\n💙 Еженедельная аналитика и поддержка"),
    "TG_DESIGN": Product("TG_DESIGN", "🎨 Оформление Telegram канала", 500,
        "• Уникальный стиль\n• Шапка/шаблоны\n• Палитра/шрифты\n• Рост узнаваемости"),
    "VK_DESIGN": Product("VK_DESIGN", "🔥 Оформление группы ВК", 500,
        "• Шапка/меню\n• Обложки\n• Шаблоны постов\n• Оптимизация под ЦА"),
}

CART: Dict[int, Dict[str, int]] = {}
CART_LOCK = Lock()
ASK_CONTACT, ASK_NOTE, ASK_TXN = range(3)
ASK_QUESTION = 1001
DIV = "─"*42

def menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["Каталог","Корзина"],["📞 Задать вопрос","💬 Связаться с админом"]], resize_keyboard=True)

def catalog_ikb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"{p.title} — {p.price}₽", callback_data=f"view:{p.id}")] for p in PRODUCTS.values()]
    return InlineKeyboardMarkup(rows)

def product_ikb(pid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("➕ В корзину", callback_data=f"add:{pid}")],
                                 [InlineKeyboardButton("⬅️ Назад к каталогу", callback_data="back:catalog")]])

def cart_ikb(has_items: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_items:
        rows += [[InlineKeyboardButton("✅ Оформить заказ", callback_data="checkout")],
                 [InlineKeyboardButton("🧹 Очистить корзину", callback_data="clear")]]
    rows += [[InlineKeyboardButton("⬅️ К каталогу", callback_data="back:catalog")]]
    return InlineKeyboardMarkup(rows)

def get_cart(uid:int) -> Dict[str,int]:
    with CART_LOCK:
        return CART.setdefault(uid, {})

def cart_summary(uid:int) -> Tuple[str,int]:
    items = get_cart(uid)
    if not items: return ("Ваша корзина пуста.",0)
    lines=[f"<b>🧺 Корзина</b>\n{DIV}"]; total=0
    for pid,qty in items.items():
        p=PRODUCTS.get(pid); 
        if not p: continue
        s=p.price*qty; total+=s
        lines.append(f"• {p.title} × {qty} = <b>{s}₽</b>")
    lines.append(f"{DIV}\n<b>Итого: {total}₽</b>")
    return ("\n".join(lines), total)

def append_order(order:dict)->None:
    data=[]
    if ORDERS_FILE.exists():
        try: data=json.loads(ORDERS_FILE.read_text("utf-8"))
        except: data=[]
    data.append(order)
    ORDERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def user_mention(u)->str:
    if getattr(u,"username",None): return f"@{u.username}"
    name=f"{u.first_name or ''} {u.last_name or ''}".strip()
    return name or f"id:{u.id}"

# ——— Handlers каталога/корзины
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Добро пожаловать в BoostX!\n\nНажмите «Каталог» чтобы выбрать услугу.",
        reply_markup=menu_kb()
    )

async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    header=f"<b>Каталог услуг</b>\n{DIV}\nВыберите услугу ниже:"
    if update.message:
        await update.message.reply_text(header, parse_mode=ParseMode.HTML)
        await update.message.reply_text("▼", reply_markup=catalog_ikb())
    else:
        q=update.callback_query
        await q.message.edit_text(header, parse_mode=ParseMode.HTML, reply_markup=catalog_ikb())
        await q.answer()

async def view_product_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    pid=q.data.split(":",1)[1]
    p=PRODUCTS.get(pid)
    if not p: 
        await q.answer("Услуга не найдена", show_alert=True); return
    text=f"<b>{p.title}</b>\n{DIV}\n{p.description}\n\nЦена: <b>{p.price}₽</b>"
    await q.message.edit_text(text, reply_markup=product_ikb(p.id), parse_mode=ParseMode.HTML)
    await q.answer()

async def add_to_cart_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    pid=q.data.split(":",1)[1]
    if pid not in PRODUCTS: 
        await q.answer("Услуга не найдена", show_alert=True); return
    items=get_cart(q.from_user.id); items[pid]=items.get(pid,0)+1
    await q.answer("Добавлено в корзину")
    text,_=cart_summary(q.from_user.id)
    await q.message.edit_text(text, reply_markup=cart_ikb(True), parse_mode=ParseMode.HTML)

async def back_catalog_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_catalog(update, context)

async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    text,total=cart_summary(uid)
    await update.message.reply_text(text, reply_markup=cart_ikb(bool(get_cart(uid))), parse_mode=ParseMode.HTML)

async def clear_cart_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    with CART_LOCK:
        CART[q.from_user.id]={}
    await q.answer("Корзина очищена")
    text,_=cart_summary(q.from_user.id)
    await q.message.edit_text(text, reply_markup=cart_ikb(False), parse_mode=ParseMode.HTML)

# ——— Оформление
async def checkout_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    items=get_cart(q.from_user.id)
    if not items:
        await q.answer("Корзина пуста", show_alert=True)
        return ConversationHandler.END
    user=q.from_user
    username=f"@{user.username}" if user.username else None
    if username:
        context.user_data["contact"]=username
        await q.message.edit_text(
            f"<b>Оформление заказа</b>\n{DIV}\nВаш username: {username}\n\nТеперь напишите комментарий/пожелания (по желанию).",
            parse_mode=ParseMode.HTML
        )
        return ASK_NOTE
    else:
        await q.message.edit_text(
            f"<b>Оформление заказа</b>\n{DIV}\nУ вас нет публичного @username.\nНапишите контакт (ник или телефон).",
            parse_mode=ParseMode.HTML
        )
        return ASK_CONTACT

async def ask_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "contact" not in context.user_data:
        context.user_data["contact"]=update.message.text.strip()
        await update.message.reply_text("Спасибо! Теперь укажите комментарий к заказу (по желанию).")
        return ASK_NOTE
    context.user_data["note"]=update.message.text.strip()
    await update.message.reply_text(
        f"<b>Оплата</b>\n{DIV}\nОплатите по ссылке:\n<a href=\"{CARD_DETAILS}\">{CARD_DETAILS}</a>\n\n{PAY_INSTRUCTIONS}\n\nПосле оплаты пришлите номер транзакции/чека.",
        parse_mode=ParseMode.HTML
    )
    return ASK_TXN

async def ask_txn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["note"]=update.message.text.strip()
    await update.message.reply_text(
        f"<b>Оплата</b>\n{DIV}\nОплатите по ссылке:\n<a href=\"{CARD_DETAILS}\">{CARD_DETAILS}</a>\n\n{PAY_INSTRUCTIONS}\n\nПосле оплаты пришлите номер транзакции/чека.",
        parse_mode=ParseMode.HTML
    )
    return ASK_TXN

async def finish_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user=update.message.from_user; uid=user.id
    txn=update.message.text.strip()
    items=get_cart(uid); _,total=cart_summary(uid)
    order={
        "timestamp": datetime.utcnow().isoformat()+"Z",
        "user_id": uid,
        "user": {"username": user.username, "first_name": user.first_name, "last_name": user.last_name},
        "items": [{"id": pid, "title": PRODUCTS[pid].title, "qty": qty, "price": PRODUCTS[pid].price} for pid,qty in items.items()],
        "total": total, "contact": context.user_data.get("contact"), "note": context.user_data.get("note"), "transaction": txn,
    }
    append_order(order)
    if ADMIN_ID:
        cart_lines="\n".join(f"• {PRODUCTS[pid].title} × {qty} = {PRODUCTS[pid].price*qty}₽" for pid,qty in items.items())
        admin_text=(f"🧾 <b>Новый заказ</b>\n{DIV}\nПокупатель: {user_mention(user)} (id {uid})\n"
                    f"Контакт: {order['contact']}\nКомментарий: {order['note']}\n\n{cart_lines}\n\n"
                    f"<b>Итого: {total}₽</b>\nТранзакция/чек: <code>{txn}</code>")
        try: await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode=ParseMode.HTML)
        except: pass
    with CART_LOCK:
        CART[uid]={}
    await update.message.reply_text("Спасибо! Заказ оформлен. Мы свяжемся с вами в ближайшее время.", reply_markup=menu_kb())
    return ConversationHandler.END

async def cancel_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Оформление отменено.", reply_markup=menu_kb())
    return ConversationHandler.END

# ——— Вопрос/поддержка
async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✏️ Напишите ваш вопрос — мы ответим в этом чате.", reply_markup=ReplyKeyboardMarkup([["❌ Отменить оформление"]], resize_keyboard=True, one_time_keyboard=True))
    return 1001

async def forward_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user=update.message.from_user; text=update.message.text.strip()
    admin_text=(f"📩 <b>Новый вопрос</b>\n{DIV}\nОт: {user_mention(user)} (id {user.id})\n\n<b>Текст:</b>\n{text}\n\n"
                f"✏️ Чтобы ответить — пришлите:\n/reply {user.id} ваш_текст")
    if ADMIN_ID:
        try: await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode=ParseMode.HTML)
        except: pass
    await update.message.reply_text("✅ Вопрос передан. Ответ придёт сюда.", reply_markup=menu_kb())
    return ConversationHandler.END

async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_ID: return
    if len(context.args)<2:
        await update.message.reply_text("Использование: /reply user_id текст"); return
    try: user_id=int(context.args[0])
    except: await update.message.reply_text("Неверный user_id."); return
    reply_text=" ".join(context.args[1:]).strip()
    if not reply_text: await update.message.reply_text("Пустой ответ."); return
    try:
        await context.bot.send_message(chat_id=user_id, text=f"💬 Ответ администратора:\n\n{reply_text}")
        await update.message.reply_text("✅ Сообщение отправлено пользователю.")
    except Exception as e:
        await update.message.reply_text(f"Не удалось отправить: {e}")

# ——— Регистрация интеграции баланса/LookSMM
from handlers.balance_pay import register_balance_handlers

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
            1001: [
                MessageHandler(filters.Regex(r"^❌ Отменить оформление$"), cancel_checkout),
                MessageHandler(filters.TEXT & ~filters.COMMAND, forward_question),
            ],
        },
        fallbacks=[MessageHandler(filters.Regex(r"^❌ Отменить оформление$"), cancel_checkout)],
        allow_reentry=True,
    )
    app.add_handler(ask_conv)

    app.add_handler(MessageHandler(filters.Regex("^💬 Связаться с админом$"),
            lambda u,c: u.message.reply_text("📬 Напиши напрямую: @Delay34", reply_markup=menu_kb())))

    app.add_handler(CommandHandler("reply", reply_command))

    # Баланс/оплата/LookSMM
    register_balance_handlers(app)

    return app

if __name__ == "__main__":
    application = build_application()
    print("✅ Bot is running on Render (BoostX)")
    application.run_polling()
