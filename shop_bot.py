
# -*- coding: utf-8 -*-
from __future__ import annotations
import os, json, asyncio, time, uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
from aiohttp import web
import requests

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, Defaults, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, ContextTypes, filters
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN","").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID","0"))
LOOKSMM_KEY = os.getenv("LOOKSMM_KEY","").strip()
PAY_URL = os.getenv("PAY_URL","https://www.tinkoff.ru/rm/r_nIutIhQtbX.tRouMxMcdC/kgUL962390")

CATALOG_PATH = Path("config/config.json")
MAP_PATH = Path("config/service_map.json")

BALANCES_FILE = Path("balances.json")
ORDERS_FILE = Path("orders.json")
INVOICES_FILE = Path("invoices.json")

def _read_json(path: Path, default):
    try:
        if not path.exists(): return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def _write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def load_catalog() -> Dict[str, Any]:
    data = _read_json(CATALOG_PATH, {"pricing_multiplier":1.0, "categories":[]})
    data.setdefault("pricing_multiplier", 1.0)
    data.setdefault("categories", [])
    return data

def load_map() -> Dict[str, int]:
    raw = _read_json(MAP_PATH, {"map":[]})
    mapping = {}
    for row in raw.get("map", []):
        cat = (row.get("cat") or "").strip()
        item = (row.get("item") or "").strip()
        sid = row.get("service_id")
        if cat and item and sid:
            key = f"{cat}:::{item}"
            try:
                mapping[key] = int(sid)
            except Exception:
                pass
    return mapping

def get_balance(user_id: int) -> float:
    rows = _read_json(BALANCES_FILE, [])
    for r in rows:
        if r.get("user_id")==user_id:
            return float(r.get("balance",0))
    return 0.0

def set_balance(user_id: int, value: float) -> float:
    rows = _read_json(BALANCES_FILE, [])
    for r in rows:
        if r.get("user_id")==user_id:
            r["balance"] = float(value); _write_json(BALANCES_FILE, rows); return float(value)
    rows.append({"user_id": user_id, "balance": float(value)})
    _write_json(BALANCES_FILE, rows)
    return float(value)

def add_balance(user_id: int, delta: float) -> float:
    return set_balance(user_id, get_balance(user_id)+float(delta))

def create_invoice(user_id: int, amount: float, note: str="") -> dict:
    inv = {
        "invoice_id": uuid.uuid4().hex,
        "user_id": user_id,
        "amount": float(amount),
        "note": note,
        "status": "pending",
        "created_at": int(time.time()),
        "paid_at": None
    }
    data = _read_json(INVOICES_FILE, []); data.append(inv); _write_json(INVOICES_FILE, data)
    return inv

def confirm_invoice(invoice_id: str) -> dict|None:
    data = _read_json(INVOICES_FILE, [])
    for inv in data:
        if inv.get("invoice_id")==invoice_id and inv.get("status")!="paid":
            inv["status"]="paid"; inv["paid_at"]=int(time.time())
            _write_json(INVOICES_FILE, data)
            add_balance(inv["user_id"], inv["amount"])
            return inv
    return None

def append_order(order: dict):
    rows = _read_json(ORDERS_FILE, [])
    order["created_at"] = int(time.time())
    rows.append(order); _write_json(ORDERS_FILE, rows)

def looksmm_services() -> List[dict]:
    if not LOOKSMM_KEY: raise RuntimeError("LOOKSMM_KEY is not set")
    url = "https://looksmm.ru/api/v2"
    r = requests.get(url, params={"action":"services","key":LOOKSMM_KEY}, timeout=30)
    r.raise_for_status(); return r.json()

def looksmm_add(service_id: int, link: str, quantity: int) -> Any:
    if not LOOKSMM_KEY: raise RuntimeError("LOOKSMM_KEY is not set")
    url = "https://looksmm.ru/api/v2"
    r = requests.get(url, params={
        "action": "add",
        "service": service_id,
        "link": link,
        "quantity": quantity,
        "key": LOOKSMM_KEY
    }, timeout=30)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return r.text

def price_str(price: float, unit: str, mult: float) -> str:
    p = float(price) * float(mult)
    tail = "за 1000" if unit=="per_1000" else "за 100"
    return f"{p:.2f} ₽ {tail}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Добро пожаловать в <b>BoostX</b> — платформу профессионального продвижения.\n\n"
        "Мы помогаем развивать <b>Telegram</b>, <b>YouTube</b> и <b>TikTok</b> "
        "с быстрыми и надёжными результатами.\n\n"
        "Откройте каталог, чтобы выбрать услугу, или воспользуйтесь кнопками ниже "
        "для управления балансом и связи с поддержкой."
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Каталог", callback_data="catalog"), InlineKeyboardButton("👤 Профиль", callback_data="profile")],
        [
            InlineKeyboardButton("💳 Баланс", callback_data="balance"),
            InlineKeyboardButton("💳 Пополнить", callback_data="topup")
        ],
        [InlineKeyboardButton("🆘 Поддержка", callback_data="support")]
    ])

    chat_id = update.effective_chat.id

    # 1) отправляем картинку (если файл есть в проекте)
    image_paths = [
        "assets/start.png",
        "assets/welcome.png",
        "Добро пожаловать.png",
        "welcome.png",
    ]
    for p in image_paths:
        try:
            with open(p, "rb") as f:
                await context.bot.send_photo(chat_id=chat_id, photo=f)
            break
        except FileNotFoundError:
            continue
        except Exception:
            # если что-то пошло не так — просто пропускаем картинку
            break

    # 2) отправляем текст + кнопки
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=kb,
        parse_mode=ParseMode.HTML
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📘 Команды:\n"
        "/start — приветствие\n"
        "/catalog — каталог услуг\n"
        "/balance — баланс\n"
        "/topup &lt;сумма&gt; — пополнить баланс\n"
        "/confirm_payment &lt;invoice_id&gt; — подтверждение оплаты (админ)\n"
    )
    await update.message.reply_html(text)

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_html(f"💳 <b>Ваш баланс:</b> <code>{get_balance(uid):.2f} ₽</code>")

async def balance_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    await q.message.reply_html(f"💳 <b>Ваш баланс:</b> <code>{get_balance(uid):.2f} ₽</code>")

async def profile_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    username = q.from_user.username or "-"
    bal = get_balance(uid)

    rows = _read_json(ORDERS_FILE, [])
    user_orders = [o for o in rows if int(o.get("user_id", 0)) == int(uid)]
    count = len(user_orders)
    last = max(user_orders, key=lambda o: int(o.get("created_at", 0)), default=None)

    text = (
        "👤 <b>Ваш профиль</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"🔗 Username: <code>@{username}</code>\n"
        f"💳 Баланс: <code>{bal:.2f} ₽</code>\n"
        f"📦 Заказов: <code>{count}</code>\n"
    )
    if last:
        oid = last.get("order_id", "-")
        provider = last.get("provider_order_id", last.get("provider_order", "-"))
        title = last.get("title", last.get("service_title", "Услуга"))
        text += (
            "\n<b>Последний заказ</b>\n"
            f"• Услуга: <code>{title}</code>\n"
            f"• ID: <code>{oid}</code>\n"
            f"• Provider ID: <code>{provider}</code>\n"
        )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Каталог", callback_data="catalog")],
        [
            InlineKeyboardButton("💳 Баланс", callback_data="balance"),
            InlineKeyboardButton("💳 Пополнить", callback_data="topup"),
        ],
        [InlineKeyboardButton("🆘 Поддержка", callback_data="support")],
    ])
    await q.message.reply_html(text, reply_markup=kb)

async def topup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_html(
            "Использование: <code>/topup &lt;сумма&gt;</code>\n"
            f"Ссылка на оплату: {PAY_URL}\n\n"
            "В сообщении к переводу укажите: ваш @username и номер счёта (invoice_id), который я пришлю после /topup."
        )
        return
    try:
        amount = float(args[0].replace(",", "."))
        if amount <= 0: raise ValueError
    except Exception:
        await update.message.reply_text("Сумма должна быть положительным числом.")
        return
    inv = create_invoice(update.effective_user.id, amount, note=f"user={update.effective_user.username}")
    await update.message.reply_html(
        f"🧾 <b>Счёт создан:</b> <code>{inv['invoice_id']}</code>\n"
        f"Сумма: <b>{amount:.2f} ₽</b>\n\n"
        f"Оплатите по ссылке: {PAY_URL}\n"
        "В сообщении к переводу укажите: ваш @username и номер счёта (invoice_id)."
    )

async def confirm_payment_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_html("Использование: <code>/confirm_payment &lt;invoice_id&gt;</code>")
        return
    inv = confirm_invoice(context.args[0])
    if not inv:
        await update.message.reply_text("Счёт не найден или уже оплачен.")
    else:
        await update.message.reply_text(f"✅ Пополнение зачтено. Баланс +{inv['amount']:.2f} ₽")

async def give_balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("Использование: /give_balance <user_id> <amount>")
        return
    try:
        target_id = int(args[0])
        amount = float(str(args[1]).replace(",", "."))
    except Exception:
        await update.message.reply_text("Неверные параметры. Пример: /give_balance 123456 50")
        return

    new_bal = add_balance(target_id, amount)
    await update.message.reply_text(f"✅ Начислено {amount:.2f} ₽ пользователю {target_id}. Новый баланс: {new_bal:.2f} ₽")

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"🎁 Вам начислен баланс: +{amount:.2f} ₽\nВаш баланс: {new_bal:.2f} ₽"
        )
    except Exception:
        pass

async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    # 1️⃣ картинка для кнопки «Каталог»
    chat_id = update.effective_chat.id
    await context.bot.send_photo(
        chat_id=chat_id,
        photo=open("assets/catalog.png", "rb")
    )

    data = load_catalog()
    cats = data.get("categories", [])
    if not cats:
        target = query.message if query else update.message
        await target.reply_text("Каталог временно пуст.")
        return
    buttons = [[InlineKeyboardButton(c.get("title","Категория"), callback_data=f"cat_{i}")] for i,c in enumerate(cats)]
    kb = InlineKeyboardMarkup(buttons)
    target = query.message if query else update.message
    await target.reply_html("<b>📋 Каталог BoostX</b>\n\nВыберите категорию:", reply_markup=kb)

async def show_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    data = load_catalog(); cats = data.get("categories", [])
    try:
        idx = int(q.data.split("_")[1])
    except Exception:
        await q.answer("Ошибка категории"); return
    if idx < 0 or idx >= len(cats):
        await q.answer("Категория не найдена"); return
    cat = cats[idx]
    title = cat.get("title","Категория")
    unit = cat.get("unit","per_1000")
    mult = float(data.get("pricing_multiplier", 1.0))
    rows = []
    for i, item in enumerate(cat.get("items", [])):
        item_unit = item.get("unit", unit)
        label = f"{item.get('title','Услуга')} — {price_str(item.get('price',0), item_unit, mult)}"
        rows.append([InlineKeyboardButton(label[:64], callback_data=f"item_{idx}_{i}")])
    rows.append([InlineKeyboardButton("⬅️ Назад к категориям", callback_data="catalog")])
    await q.message.reply_html(f"<b>{title}</b>\nВыберите услугу:", reply_markup=InlineKeyboardMarkup(rows))

LINK, QTY, CONFIRM = range(3)

async def order_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    _, cidx, iidx = q.data.split("_"); cidx = int(cidx); iidx = int(iidx)
    data = load_catalog()
    try:
        cat = data["categories"][cidx]; item = cat["items"][iidx]
    except Exception:
        await q.message.reply_text("Ошибка выбора услуги."); return ConversationHandler.END
    context.user_data["order"] = {
        "cat_idx": cidx, "item_idx": iidx,
        "cat_title": cat.get("title","Категория"),
        "unit": item.get("unit", cat.get("unit","per_1000")),
        "mult": float(data.get("pricing_multiplier",1.0)),
        "title": item.get("title","Услуга"),
        "price": float(item.get("price",0))
    }
    await q.message.reply_text("🔗 Отправьте ссылку (URL), на которую оформляем заказ:")
    return LINK

async def order_get_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = (update.message.text or "").strip()
    if not (link.startswith("http://") or link.startswith("https://") or ".com" in link or ".ru" in link):
        await update.message.reply_text("Похоже, это не ссылка. Отправьте корректный URL:")
        return LINK
    context.user_data["order"]["link"] = link
    await update.message.reply_text("🔢 Укажите количество (целое число):")
    return QTY

def compute_cost(price: float, unit: str, mult: float, qty: int) -> float:
    base = 1000.0 if unit=="per_1000" else 100.0
    return float(price) * float(mult) * (qty / base)

def resolve_service_id(cat_title: str, item_title: str) -> int|None:
    m = load_map()
    return m.get(f"{cat_title}:::{item_title}")

def ensure_qty_limits(service_id: int, qty: int) -> Tuple[int,int,int]:
    try:
        svcs = looksmm_services()
        svc = next((s for s in svcs if int(s.get("service",0))==int(service_id)), None)
        if not svc:
            return qty, None, None
        try:
            min_q = int(float(svc.get("min", 1)))
            max_q = int(float(svc.get("max", 1000000)))
        except Exception:
            return qty, None, None
        return max(min_q, min(qty, max_q)), min_q, max_q
    except Exception:
        return qty, None, None

async def order_get_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    if not txt.isdigit():
        await update.message.reply_text("Количество должно быть целым числом. Введите ещё раз:")
        return QTY
    qty = int(txt)
    if qty <= 0:
        await update.message.reply_text("Количество должно быть больше 0. Введите ещё раз:")
        return QTY

    info = context.user_data.get("order", {})
    sid = resolve_service_id(info.get("cat_title","Категория"), info.get("title","Услуга"))
    if not sid:
        await update.message.reply_text("Эта позиция не привязана к поставщику. Добавьте в service_map.json соответствующий service_id.")
        return ConversationHandler.END

    # validate limits
    adj_qty, min_q, max_q = await asyncio.to_thread(ensure_qty_limits, int(sid), qty)
    if min_q is not None and qty < min_q:
        await update.message.reply_text(f"Минимум для этой услуги: {min_q}. Отправьте новое количество:")
        return QTY
    if max_q is not None and qty > max_q:
        await update.message.reply_text(f"Максимум для этой услуги: {max_q}. Отправьте новое количество:")
        return QTY

    # сохраняем данные и просим подтверждение
    qty = int(adj_qty)
    cost = compute_cost(info["price"], info["unit"], info["mult"], qty)
    uid = update.effective_user.id
    bal = get_balance(uid)
    if bal < cost:
        await update.message.reply_text(
            f"Недостаточно средств. Нужно {cost:.2f} ₽, на балансе {bal:.2f} ₽.\nПополнить: /topup <сумма>"
        )
        context.user_data.pop("order", None)
        return ConversationHandler.END

    info["service_id"] = int(sid)
    info["qty"] = int(qty)
    info["cost"] = float(cost)
    context.user_data["order"] = info

    text = (
        "✅ <b>Подтверждение заказа</b>\n\n"
        f"• Услуга: <code>{info.get('title','Услуга')}</code>\n"
        f"• Кол-во: <code>{qty}</code>\n"
        f"• Ссылка: <code>{info.get('link','')}</code>\n"
        f"• Стоимость: <code>{cost:.2f} ₽</code>\n"
        f"• Баланс: <code>{bal:.2f} ₽</code>\n\n"
        "Подтвердить оформление?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_order")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_order")],
    ])
    await update.message.reply_html(text, reply_markup=kb)
    return CONFIRM

async def order_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    info = context.user_data.get("order", {})
    uid = q.from_user.id

    sid = int(info.get("service_id", 0))
    qty = int(info.get("qty", 0))
    cost = float(info.get("cost", 0.0))
    link = info.get("link", "")

    if not sid or qty <= 0 or not link:
        await q.message.reply_text("Данные заказа не найдены. Откройте каталог и оформите заказ заново.")
        context.user_data.pop("order", None)
        return ConversationHandler.END

    bal = get_balance(uid)
    if bal < cost:
        await q.message.reply_html(
            f"Недостаточно средств. Нужно <code>{cost:.2f} ₽</code>, на балансе <code>{bal:.2f} ₽</code>."
        )
        context.user_data.pop("order", None)
        return ConversationHandler.END

    # списываем перед созданием
    set_balance(uid, bal - cost)

    try:
        res = await asyncio.to_thread(looksmm_add, sid, link, qty)
        if isinstance(res, dict):
            provider_order_id = res.get("order")
        else:
            provider_order_id = None
        if not provider_order_id:
            raise RuntimeError(f"LooksMM response: {res}")

        order_id = str(uuid.uuid4())[:8]
        save_order({
            "order_id": order_id,
            "user_id": uid,
            "username": q.from_user.username or "",
            "title": info.get("title","Услуга"),
            "service_id": sid,
            "qty": qty,
            "cost": cost,
            "link": link,
            "provider_order_id": provider_order_id,
        })

        # уведомление админу о новом заказе
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "🆕 Новый заказ\n\n"
                    f"User: {uid} (@{q.from_user.username or '-'})\n"
                    f"Услуга: {info.get('title','Услуга')}\n"
                    f"service_id: {sid}\n"
                    f"qty: {qty}\n"
                    f"cost: {cost:.2f} ₽\n"
                    f"link: {link}\n"
                    f"provider_order_id: {provider_order_id}\n"
                    f"order_id: {order_id}"
                )
            )
        except Exception:
            pass

        # статус-экран после оформления
        status_text = (
            "✅ <b>Заказ создан!</b>\n\n"
            f"• Услуга: <code>{info.get('title','Услуга')}</code>\n"
            f"• Кол-во: <code>{qty}</code>\n"
            f"• Списано: <code>{cost:.2f} ₽</code>\n"
            f"• ID заказа: <code>{order_id}</code>\n"
            f"• Provider ID: <code>{provider_order_id}</code>\n"
        )
        status_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 Профиль", callback_data="profile"), InlineKeyboardButton("📋 Каталог", callback_data="catalog")],
            [InlineKeyboardButton("🆘 Поддержка", callback_data="support")],
        ])
        await q.message.reply_html(status_text, reply_markup=status_kb)

    except Exception as e:
        # откат баланса
        set_balance(uid, bal)
        await q.message.reply_text(f"Ошибка создания заказа: {e}")

    context.user_data.pop("order", None)
    return ConversationHandler.END


async def order_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data.pop("order", None)
    await q.message.reply_text("Оформление отменено.")
    return ConversationHandler.END

async def order_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("order", None)
    await update.message.reply_text("Оформление отменено.")
    return ConversationHandler.END

# Simple health server for Render
async def _start_http_server(app_obj):
    async def health(_request):
        return web.Response(text="ok")
    http_app = web.Application()
    http_app.router.add_get("/", health)
    http_app.router.add_get("/healthz", health)
    port = int(os.getenv("PORT", "10000"))
    runner = web.AppRunner(http_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 HTTP server started on 0.0.0.0:{port}")
    app_obj.bot_data["http_runner"] = runner

async def _post_init(app: Application):
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        print("✅ Webhook удалён, polling активирован.")
    except Exception as e:
        print(f"⚠️ Ошибка удаления webhook: {e}")
    try:
        await _start_http_server(app)
    except Exception as e:
        print(f"⚠️ HTTP server start error: {e}")



# --------- Дополнительные обработчики BoostX (баланс, категории платформ, поддержка) ---------


async def topup_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Инлайн-инструкция по пополнению баланса (аналог /topup без суммы)."""
    q = update.callback_query
    await q.answer()
    text = (
        "Чтобы пополнить баланс, используйте эту инструкцию:\n"
        "Использование: <code>/topup &lt;сумма&gt;</code>\n"
        f"Ссылка на оплату: {PAY_URL}\n\n"
        "В сообщении к переводу укажите: ваш @username и номер счёта (invoice_id), "
        "который бот пришлёт после команды /topup."
    )
    await q.message.reply_html(text)





# Поддержка и ответы админа
SUPPORT_STATE = 10

async def support_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    text = (
        "🆘 <b>Поддержка BoostX</b>\n\n"
        "Опишите, пожалуйста, ваш вопрос одним сообщением. Я передам его администратору, "
        "и ответ придёт сюда же.\n\n"
        "Чтобы отменить, отправьте /cancel."
    )
    await q.message.reply_html(text)
    return SUPPORT_STATE


async def support_collect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg_text = (update.message.text or "").strip()
    if not msg_text:
        await update.message.reply_text("Сообщение пустое. Отправьте, пожалуйста, текст вопроса.")
        return SUPPORT_STATE

    # Пересылаем вопрос администратору
    header = (
        "❓ <b>Новое обращение в поддержку</b>\n\n"
        f"От: @{user.username or 'без username'} (ID: <code>{user.id}</code>)\n\n"
        f"{msg_text}\n\n"
        f"Для ответа используйте: <code>/reply {user.id} &lt;текст ответа&gt;</code>"
    )
    try:
        if ADMIN_ID:
            await context.bot.send_message(ADMIN_ID, header, parse_mode=ParseMode.HTML)
    except Exception:
        # Не падаем, если админ недоступен
        pass

    await update.message.reply_text(
        "Ваше сообщение отправлено в поддержку. Ответ придёт в этот чат, как только администратор его напишет."
    )
    return ConversationHandler.END


async def support_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Обращение в поддержку отменено.")
    return ConversationHandler.END


async def reply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для администраторов: /reply user_id текст"""
    if update.effective_user.id != ADMIN_ID:
        # тихо игнорируем, чтобы не светить админские команды
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("Использование: /reply [user_id] [сообщение]")
        return
    try:
        target_id = int(args[0])
    except Exception:
        await update.message.reply_text("Неверный user_id.")
        return
    text = " ".join(args[1:])
    try:
        await context.bot.send_message(target_id, f"💬 Ответ от поддержки BoostX:\n\n{text}")
        await update.message.reply_text("Ответ отправлен пользователю.")
    except Exception:
        await update.message.reply_text(
            "Не удалось отправить сообщение пользователю. Возможно, он не писал боту или заблокировал его."
        )

def build_application():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .defaults(Defaults(parse_mode=ParseMode.HTML))
        .post_init(_post_init)
        .build()
    )
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("topup", topup_cmd))
    app.add_handler(CommandHandler("confirm_payment", confirm_payment_cmd))
    app.add_handler(CommandHandler("give_balance", give_balance_cmd))
    app.add_handler(CommandHandler("reply", reply_cmd))

    # Каталог / услуги
    app.add_handler(CommandHandler("catalog", show_catalog))
    app.add_handler(CommandHandler("services", show_catalog))
    app.add_handler(CallbackQueryHandler(show_catalog, pattern="^catalog"))
    app.add_handler(CallbackQueryHandler(show_category, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(balance_cb, pattern="^balance$"))
    app.add_handler(CallbackQueryHandler(topup_cb, pattern="^topup$"))
    app.add_handler(CallbackQueryHandler(profile_cb, pattern="^profile$"))

    # Оформление заказов
    conv_order = ConversationHandler(
        entry_points=[CallbackQueryHandler(order_entry, pattern="^item_")],
        states={
            0: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_get_link)],
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_get_qty)],
            2: [CallbackQueryHandler(order_confirm, pattern="^confirm_order$"), CallbackQueryHandler(order_cancel_cb, pattern="^cancel_order$")],
        },
        fallbacks=[CommandHandler("cancel", order_cancel)],
        name="order_conv",
        persistent=False,
    )
    app.add_handler(conv_order)

    # Поддержка
    conv_support = ConversationHandler(
        entry_points=[CallbackQueryHandler(support_entry, pattern="^support$")],
        states={
            SUPPORT_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_collect)],
        },
        fallbacks=[CommandHandler("cancel", support_cancel)],
        name="support_conv",
        persistent=False,
    )

    app.add_handler(conv_support)

    return app

if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set")
    print("🚀 Bot is running...")
    application = build_application()
    application.run_polling(drop_pending_updates=True)
