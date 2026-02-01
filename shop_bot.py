
# -*- coding: utf-8 -*-
from __future__ import annotations
import os, json, asyncio, time, uuid, re
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
USERS_FILE = Path("users.json")
EXPENSES_FILE = Path("expenses.json")

PROMO_CODES_PATH = Path("config/promo_codes.json")
PROMO_USES_FILE = Path("promo_uses.json")

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
    raw = _read_json(MAP_PATH, {})
    # New format: {"items": {"telegram_1273": 1273, ...}}
    items = raw.get("items")
    if isinstance(items, dict):
        mapping: Dict[str, int] = {}
        for k, v in items.items():
            try:
                mapping[str(k).strip()] = int(v)
            except Exception:
                continue
        return mapping

    # Legacy format: {"map": [{"cat": "...", "item": "...", "service_id": 123}, ...]}
    mapping: Dict[str, int] = {}
    for row in (raw.get("map") or []):
        try:
            cat = (row.get("cat") or "").strip()
            item = (row.get("item") or "").strip()
            sid = row.get("service_id")
            if cat and item and sid:
                mapping[f"{cat}:::{item}"] = int(sid)
        except Exception:
            continue
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

def _load_users() -> dict:
    return _read_json(USERS_FILE, {"users": []})

def _save_users(data: dict):
    _write_json(USERS_FILE, data)

def remember_user(user_id: int):
    """Store user_id for broadcasts/stats. Safe to call often."""
    try:
        uid = int(user_id)
    except Exception:
        return
    data = _load_users()
    lst = data.setdefault("users", [])
    if uid not in lst:
        lst.append(uid)
        _save_users(data)

def get_all_user_ids() -> List[int]:
    """Best-effort list of known users (users.json + balances/orders/invoices)."""
    ids = set()
    try:
        for uid in (_load_users().get("users") or []):
            try: ids.add(int(uid))
            except Exception: pass
    except Exception:
        pass

    for row in (_read_json(BALANCES_FILE, []) or []):
        if isinstance(row, dict) and "user_id" in row:
            try: ids.add(int(row["user_id"]))
            except Exception: pass

    for inv in (_read_json(INVOICES_FILE, []) or []):
        if isinstance(inv, dict) and "user_id" in inv:
            try: ids.add(int(inv["user_id"]))
            except Exception: pass

    for o in (_read_json(ORDERS_FILE, []) or []):
        if isinstance(o, dict) and "user_id" in o:
            try: ids.add(int(o["user_id"]))
            except Exception: pass

    ids.discard(0)
    return sorted(ids)




def _load_promo_codes() -> dict:
    return _read_json(PROMO_CODES_PATH, {})

def _save_promo_codes(data: dict):
    _write_json(PROMO_CODES_PATH, data)

def _load_promo_uses() -> dict:
    return _read_json(PROMO_USES_FILE, {"users": {}})

def _save_promo_uses(data: dict):
    _write_json(PROMO_USES_FILE, data)

def promo_is_used(user_id: int, code: str) -> bool:
    data = _load_promo_uses()
    return code.upper() in set(data.get("users", {}).get(str(user_id), []))

def promo_mark_used(user_id: int, code: str):
    data = _load_promo_uses()
    users = data.setdefault("users", {})
    lst = users.setdefault(str(user_id), [])
    code_u = code.upper()
    if code_u not in lst:
        lst.append(code_u)
    _save_promo_uses(data)

def promo_validate(code: str, base_cost: float, user_id: int, allow_for_combo: bool=False) -> tuple[bool, str, int]:
    code_u = (code or "").strip().upper()
    if not code_u:
        return False, "Введите промокод.", 0
    promos = _load_promo_codes()
    cfg = promos.get(code_u)
    if not cfg or not cfg.get("active", True):
        return False, "Промокод не найден или не активен.", 0
    percent = int(cfg.get("percent", 0) or 0)
    if percent <= 0 or percent > 90:
        return False, "Некорректная скидка у промокода.", 0
    min_total = float(cfg.get("min_total", 0) or 0)
    if min_total and float(base_cost) < min_total:
        return False, f"Промокод действует от {min_total:.0f} ₽.", 0
    if promo_is_used(user_id, code_u):
        return False, "Этот промокод уже использован вами.", 0
    if not allow_for_combo and cfg.get("no_combo", True):
        # запрещаем для комбо по умолчанию
        return True, "", percent
    return True, "", percent

def apply_discount(cost: float, percent: int) -> float:
    return max(0.0, float(cost) * (1.0 - (float(percent)/100.0)))


# --------------------
# Admin panel
# - Edit base price for one item (client price = base * pricing_multiplier)
# - Add category / item (with supplier service_id for auto-orders)
# - Add / edit / delete descriptions for categories and items
# --------------------

ADMIN_MENU, ADMIN_SELECT_CAT, ADMIN_SELECT_ITEM, ADMIN_PRICE_INPUT, ADMIN_ADD_CAT_TITLE, ADMIN_ADD_ITEM_CAT, ADMIN_ADD_ITEM_TITLE, ADMIN_ADD_ITEM_PRICE, ADMIN_ADD_ITEM_SUPPLIER, ADMIN_ADD_ITEM_SID, ADMIN_ADD_ITEM_DESC, ADMIN_DESC_MENU, ADMIN_DESC_CAT_SELECT, ADMIN_DESC_ITEM_SELECT, ADMIN_DESC_INPUT, ADMIN_DELETE_MENU, ADMIN_DELETE_CAT_SELECT, ADMIN_DELETE_ITEM_CAT, ADMIN_DELETE_ITEM_SELECT, ADMIN_DELETE_CONFIRM, ADMIN_BROADCAST_TEXT, ADMIN_STATS_MENU, ADMIN_EXPENSE_ADD_AMOUNT, ADMIN_EXPENSE_ADD_NOTE = range(20, 44)


def _is_admin(uid: int) -> bool:
    try:
        return int(uid) == int(ADMIN_ID)
    except Exception:
        return False


def _slugify(s: str) -> str:
    s = (s or '').strip().lower()
    # keep latin/digits/underscore only
    s = re.sub(r'[^a-z0-9_]+', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    return s or 'item'


def _new_item_id(cat_title: str, item_title: str) -> str:
    # stable-ish, short
    base = f"{_slugify(cat_title)[:12]}_{_slugify(item_title)[:12]}"
    return f"{base}_{uuid.uuid4().hex[:6]}"


def _admin_kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('💲 Изменить цену товара', callback_data='admin_price')],
        [InlineKeyboardButton('➕ Добавить категорию', callback_data='admin_add_cat')],
        [InlineKeyboardButton('➕ Добавить товар', callback_data='admin_add_item')],
        [InlineKeyboardButton('🗑 Удаление', callback_data='admin_delete')],
        [InlineKeyboardButton('📣 Рассылка', callback_data='admin_broadcast')],
        [InlineKeyboardButton('📊 Финансы', callback_data='admin_stats')],
        [InlineKeyboardButton('📝 Описания', callback_data='admin_desc')],
        [InlineKeyboardButton('❌ Выйти', callback_data='admin_cancel')],
    ])


def _cat_buttons(cats, prefix: str, back_cb: str = 'admin'):
    rows = []
    for i, c in enumerate(cats):
        rows.append([InlineKeyboardButton(c.get('title', f'Категория {i+1}'), callback_data=f"{prefix}{i}")])
    rows.append([InlineKeyboardButton('⬅️ Назад', callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)


def _item_buttons(cat, cidx: int, prefix: str, back_cb: str):
    rows = []
    items = cat.get('items', []) or []
    for i, it in enumerate(items):
        title = it.get('title', f'Товар {i+1}')
        rows.append([InlineKeyboardButton(title[:64], callback_data=f"{prefix}{cidx}_{i}")])
    rows.append([InlineKeyboardButton('⬅️ Назад', callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)


async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for /admin and main admin menu."""
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_admin(uid):
        return ConversationHandler.END

    kb = _admin_kb_main()
    if update.message:
        await update.message.reply_html("🛠 <b>Админ-панель</b>\n\nВыберите действие:", reply_markup=kb)
    else:
        q = update.callback_query
        if q:
            await q.answer()
            await q.message.reply_html("🛠 <b>Админ-панель</b>\n\nВыберите действие:", reply_markup=kb)
    return ADMIN_MENU


async def admin_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await admin_start(update, context)


async def admin_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer()
        await q.message.reply_text('Админ-панель закрыта.')
    return ConversationHandler.END


async def admin_cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_admin(uid):
        return ConversationHandler.END
    await update.message.reply_text('Админ-панель закрыта.')
    return ConversationHandler.END


# ----- Edit price -----
async def admin_price_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if not _is_admin(uid):
        return ConversationHandler.END

    data = load_catalog()
    cats = data.get('categories', [])
    if not cats:
        await q.message.reply_text('Категорий нет.')
        return ADMIN_MENU

    await q.message.reply_html('💲 <b>Выберите категорию</b>', reply_markup=_cat_buttons(cats, 'admin_cat_', 'admin'))
    return ADMIN_SELECT_CAT


async def admin_choose_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if not _is_admin(uid):
        return ConversationHandler.END

    # Two entry points:
    # 1) admin_cat_{i} (edit price)
    # 2) admin_desc_cat_{i} (descriptions)
    data = load_catalog()
    cats = data.get('categories', [])

    if q.data.startswith('admin_cat_'):
        try:
            cidx = int(q.data.split('_')[-1])
        except Exception:
            await q.message.reply_text('Ошибка выбора категории.')
            return ADMIN_MENU

        if cidx < 0 or cidx >= len(cats):
            await q.message.reply_text('Категория не найдена.')
            return ADMIN_MENU

        cat = cats[cidx]
        items = cat.get('items', [])
        if not items:
            await q.message.reply_text('В этой категории нет товаров.')
            return ADMIN_SELECT_CAT

        context.user_data['admin_edit'] = {'cat_idx': cidx}

        mult = float(data.get('pricing_multiplier', 1.0))
        unit_default = cat.get('unit', 'per_1000')
        rows = []
        for i, it in enumerate(items):
            base = float(it.get('price', 0) or 0)
            unit = it.get('unit', unit_default)
            label = f"{it.get('title','Товар')} — база {base:g} → {price_str(base, unit, mult)}"
            rows.append([InlineKeyboardButton(label[:64], callback_data=f"admin_item_{cidx}_{i}")])
        rows.append([InlineKeyboardButton('⬅️ Назад к категориям', callback_data='admin_price')])
        await q.message.reply_html(f"💲 <b>{cat.get('title','Категория')}</b>\n\nВыберите товар:", reply_markup=InlineKeyboardMarkup(rows))
        return ADMIN_SELECT_ITEM

    # description flow category select
    if q.data.startswith('admin_desc_cat_'):
        try:
            cidx = int(q.data.split('_')[-1])
        except Exception:
            await q.message.reply_text('Ошибка выбора категории.')
            return ADMIN_DESC_MENU
        if cidx < 0 or cidx >= len(cats):
            await q.message.reply_text('Категория не найдена.')
            return ADMIN_DESC_MENU
        context.user_data['admin_desc'] = {'target': 'category', 'cat_idx': cidx}
        cat = cats[cidx]
        desc = (cat.get('description') or '').strip()
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton('✏️ Изменить описание', callback_data='admin_desc_edit')],
            [InlineKeyboardButton('🗑 Удалить описание', callback_data='admin_desc_delete')],
            [InlineKeyboardButton('⬅️ Назад', callback_data='admin_desc_cat')],
            [InlineKeyboardButton('❌ Выйти', callback_data='admin_cancel')],
        ])
        msg = ("📝 <b>Описание категории</b>\n\n"
       f"Категория: <b>{cat.get('title','Категория')}</b>\n\n"
       "Текущее описание:\n"
       f"<code>{desc if desc else '— нет —'}</code>\n\n"
       "Выберите действие:")
        await q.message.reply_html(msg, reply_markup=kb)
        return ADMIN_DESC_MENU

    return ADMIN_MENU


async def admin_choose_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if not _is_admin(uid):
        return ConversationHandler.END

    # Two entry points:
    # 1) admin_item_{cidx}_{iidx} (edit price)
    # 2) admin_desc_item_{cidx}_{iidx} (item description)

    data = load_catalog()
    cats = data.get('categories', [])

    if q.data.startswith('admin_item_'):
        try:
            _, _, cidx, iidx = q.data.split('_')
            cidx = int(cidx); iidx = int(iidx)
        except Exception:
            await q.message.reply_text('Ошибка выбора товара.')
            return ADMIN_MENU

        if cidx < 0 or cidx >= len(cats):
            await q.message.reply_text('Категория не найдена.')
            return ADMIN_MENU
        cat = cats[cidx]
        items = cat.get('items', [])
        if iidx < 0 or iidx >= len(items):
            await q.message.reply_text('Товар не найден.')
            return ADMIN_MENU
        item = items[iidx]

        context.user_data['admin_edit'] = {'cat_idx': cidx, 'item_idx': iidx}

        mult = float(data.get('pricing_multiplier', 1.0))
        unit = item.get('unit', cat.get('unit', 'per_1000'))
        base = float(item.get('price', 0) or 0)
        shown = price_str(base, unit, mult)

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton('⬅️ Назад к товарам', callback_data=f"admin_cat_{cidx}")],
            [InlineKeyboardButton('❌ Выйти', callback_data='admin_cancel')],
        ])
        msg = ("✏️ <b>Изменение цены</b>\n\n"
       f"Товар: <b>{item.get('title','Товар')}</b>\n"
       f"Текущая база: <code>{base:g}</code>\n"
       f"Цена клиенту (x{mult:g}): <code>{shown}</code>\n\n"
       "Введите <b>новую базовую цену</b> одним сообщением (например: <code>50</code> или <code>50.5</code>):")
        await q.message.reply_html(msg, reply_markup=kb)
        return ADMIN_PRICE_INPUT

    if q.data.startswith('admin_desc_item_'):
        try:
            _, _, _, cidx, iidx = q.data.split('_')
            cidx = int(cidx); iidx = int(iidx)
        except Exception:
            await q.message.reply_text('Ошибка выбора товара.')
            return ADMIN_DESC_MENU

        if cidx < 0 or cidx >= len(cats):
            await q.message.reply_text('Категория не найдена.')
            return ADMIN_DESC_MENU
        cat = cats[cidx]
        items = cat.get('items', [])
        if iidx < 0 or iidx >= len(items):
            await q.message.reply_text('Товар не найден.')
            return ADMIN_DESC_MENU
        item = items[iidx]

        context.user_data['admin_desc'] = {'target': 'item', 'cat_idx': cidx, 'item_idx': iidx}
        desc = (item.get('description') or '').strip()
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton('✏️ Изменить описание', callback_data='admin_desc_edit')],
            [InlineKeyboardButton('🗑 Удалить описание', callback_data='admin_desc_delete')],
            [InlineKeyboardButton('⬅️ Назад', callback_data='admin_desc_item')],
            [InlineKeyboardButton('❌ Выйти', callback_data='admin_cancel')],
        ])
        msg = ("📝 <b>Описание товара</b>\n\n"
       f"Категория: <b>{cat.get('title','Категория')}</b>\n"
       f"Товар: <b>{item.get('title','Товар')}</b>\n\n"
       "Текущее описание:\n"
       f"<code>{desc if desc else '— нет —'}</code>\n\n"
       "Выберите действие:")
        await q.message.reply_html(msg, reply_markup=kb)
        return ADMIN_DESC_MENU

    return ADMIN_MENU


async def admin_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_admin(uid):
        return ConversationHandler.END

    raw = (update.message.text or '').strip().replace(',', '.')
    try:
        value = float(raw)
        if value <= 0:
            raise ValueError
    except Exception:
        await update.message.reply_text('Цена должна быть положительным числом. Пример: 50 или 50.5')
        return ADMIN_PRICE_INPUT

    edit = context.user_data.get('admin_edit') or {}
    cidx = int(edit.get('cat_idx', -1))
    iidx = int(edit.get('item_idx', -1))
    data = load_catalog()
    cats = data.get('categories', [])
    if cidx < 0 or cidx >= len(cats):
        await update.message.reply_text('Не удалось найти категорию. Откройте /admin заново.')
        return ConversationHandler.END
    items = cats[cidx].get('items', [])
    if iidx < 0 or iidx >= len(items):
        await update.message.reply_text('Не удалось найти товар. Откройте /admin заново.')
        return ConversationHandler.END

    items[iidx]['price'] = float(value)
    _write_json(CATALOG_PATH, data)

    mult = float(data.get('pricing_multiplier', 1.0))
    unit = items[iidx].get('unit', cats[cidx].get('unit', 'per_1000'))
    shown = price_str(float(value), unit, mult)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton('💲 Изменить другой товар', callback_data='admin_price')],
        [InlineKeyboardButton('🛠 В админку', callback_data='admin')],
        [InlineKeyboardButton('❌ Выйти', callback_data='admin_cancel')],
    ])
    msg = ("✅ Цена обновлена!\n\n"
       f"Новая база: <code>{float(value):g}</code>\n"
       f"Цена клиенту (x{mult:g}): <code>{shown}</code>")
    await update.message.reply_html(msg, reply_markup=kb)
    return ADMIN_MENU


# ----- Add category -----
async def admin_add_cat_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id):
        return ConversationHandler.END
    await q.message.reply_text('➕ Введите название <b>новой категории</b> одним сообщением:', parse_mode=ParseMode.HTML)
    return ADMIN_ADD_CAT_TITLE


async def admin_add_cat_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_admin(uid):
        return ConversationHandler.END

    title = (update.message.text or '').strip()
    if not title:
        await update.message.reply_text('Название не может быть пустым. Введите ещё раз:')
        return ADMIN_ADD_CAT_TITLE

    data = load_catalog()
    cats = data.get('categories', [])
    # prevent exact duplicate titles
    if any((c.get('title','').strip().lower() == title.lower()) for c in cats):
        await update.message.reply_text('Категория с таким названием уже есть. Введите другое название:')
        return ADMIN_ADD_CAT_TITLE

    cats.append({
        'title': title,
        'unit': 'per_1000',
        'description': '',
        'items': [],
    })
    data['categories'] = cats
    _write_json(CATALOG_PATH, data)

    await update.message.reply_html('✅ Категория добавлена!')
    return await admin_start(update, context)


# ----- Add item -----
async def admin_add_item_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id):
        return ConversationHandler.END

    data = load_catalog()
    cats = data.get('categories', [])
    if not cats:
        await q.message.reply_text('Сначала добавьте категорию.')
        return ADMIN_MENU

    await q.message.reply_html('➕ <b>Выберите категорию</b>, куда добавляем товар:', reply_markup=_cat_buttons(cats, 'admin_add_item_cat_', 'admin'))
    return ADMIN_ADD_ITEM_CAT


async def admin_add_item_choose_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id):
        return ConversationHandler.END

    data = load_catalog()
    cats = data.get('categories', [])
    try:
        cidx = int(q.data.split('_')[-1])
    except Exception:
        await q.message.reply_text('Ошибка выбора категории.')
        return ADMIN_MENU
    if cidx < 0 or cidx >= len(cats):
        await q.message.reply_text('Категория не найдена.')
        return ADMIN_MENU

    context.user_data['admin_new_item'] = {'cat_idx': cidx}
    await q.message.reply_text('➕ Введите <b>название товара</b> одним сообщением:', parse_mode=ParseMode.HTML)
    return ADMIN_ADD_ITEM_TITLE


async def admin_add_item_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_admin(uid):
        return ConversationHandler.END

    title = (update.message.text or '').strip()
    if not title:
        await update.message.reply_text('Название не может быть пустым. Введите ещё раз:')
        return ADMIN_ADD_ITEM_TITLE

    st = context.user_data.get('admin_new_item') or {}
    st['title'] = title
    context.user_data['admin_new_item'] = st

    await update.message.reply_text('Введите <b>базовую цену</b> (цена поставщика), например: 50 или 50.5', parse_mode=ParseMode.HTML)
    return ADMIN_ADD_ITEM_PRICE


async def admin_add_item_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_admin(uid):
        return ConversationHandler.END

    raw = (update.message.text or '').strip().replace(',', '.')
    try:
        value = float(raw)
        if value <= 0:
            raise ValueError
    except Exception:
        await update.message.reply_text('Цена должна быть положительным числом. Пример: 50 или 50.5')
        return ADMIN_ADD_ITEM_PRICE

    st = context.user_data.get('admin_new_item') or {}
    st['price'] = float(value)
    context.user_data['admin_new_item'] = st

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton('✅ Да, это накрутка (есть service_id)', callback_data='admin_add_item_supplier_yes')],
        [InlineKeyboardButton('❌ Нет, свой товар/услуга (без service_id)', callback_data='admin_add_item_supplier_no')],
    ])
    await update.message.reply_html('Товар связан с поставщиком накрутки (нужен <code>service_id</code>)?', reply_markup=kb)
    return ADMIN_ADD_ITEM_SUPPLIER


async def admin_add_item_supplier_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id):
        return ConversationHandler.END

    st = context.user_data.get('admin_new_item') or {}

    if q.data.endswith('_yes'):
        st['use_supplier'] = True
        context.user_data['admin_new_item'] = st
        await q.message.reply_text('Введите <b>ID услуги у поставщика</b> (service_id). Только число:', parse_mode=ParseMode.HTML)
        return ADMIN_ADD_ITEM_SID

    # no supplier
    st['use_supplier'] = False
    st['service_id'] = None
    context.user_data['admin_new_item'] = st
    await q.message.reply_text('📝 Введите описание товара одним сообщением.\nЕсли описание не нужно — отправьте <code>skip</code>.', parse_mode=ParseMode.HTML)
    return ADMIN_ADD_ITEM_DESC

async def admin_add_item_sid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_admin(uid):
        return ConversationHandler.END

    raw = (update.message.text or '').strip()
    if not raw.isdigit():
        await update.message.reply_text('Service ID должен быть числом. Введите ещё раз:')
        return ADMIN_ADD_ITEM_SID

    st = context.user_data.get('admin_new_item') or {}
    st['service_id'] = int(raw)
    context.user_data['admin_new_item'] = st

    await update.message.reply_text('📝 Введите описание товара одним сообщением.\nЕсли описание не нужно — отправьте <code>skip</code>.', parse_mode=ParseMode.HTML)
    return ADMIN_ADD_ITEM_DESC


async def admin_add_item_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_admin(uid):
        return ConversationHandler.END

    desc = (update.message.text or '').strip()
    if desc.lower() == 'skip':
        desc = ''

    st = context.user_data.get('admin_new_item') or {}
    cidx = int(st.get('cat_idx', -1))
    title = st.get('title', '')
    price = float(st.get('price', 0) or 0)
    service_id = st.get('service_id')

    data = load_catalog()
    cats = data.get('categories', [])
    if cidx < 0 or cidx >= len(cats):
        await update.message.reply_text('Категория не найдена. Откройте /admin заново.')
        return ConversationHandler.END

    cat = cats[cidx]
    item_id = _new_item_id(cat.get('title','cat'), title)
    cat.setdefault('items', []).append({
        'id': item_id,
        'title': title,
        'price': float(price),
        'service_id': int(service_id) if service_id is not None else None,
        'description': desc,
        'type': 'single',
    })

    _write_json(CATALOG_PATH, data)

    mult = float(data.get('pricing_multiplier', 1.0))
    unit = cat.get('unit', 'per_1000')
    shown = price_str(float(price), unit, mult)

    msg = ("✅ Товар добавлен!\n\n"
       f"Категория: <b>{cat.get('title','Категория')}</b>\n"
       f"Товар: <b>{title}</b>\n"
       f"Цена в боте (x{mult:g}): <b>{shown}</b>\n"
       f"Service ID: <code>{int(service_id)}</code>" if service_id is not None else "Service ID: <i>нет</i>")
    await update.message.reply_html(msg, disable_web_page_preview=True)
    return ADMIN_MENU


# ----- Deletion / Broadcast / Finance -----

def _expense_rows() -> List[dict]:
    return _read_json(EXPENSES_FILE, [])

def add_expense(amount: float, note: str = "") -> dict:
    row = {"amount": float(amount), "note": note, "created_at": int(time.time())}
    rows = _expense_rows()
    rows.append(row)
    _write_json(EXPENSES_FILE, rows)
    return row

def _sum_by_period(rows: List[dict], ts_field: str, now_ts: int) -> Dict[str, float]:
    # periods: day(24h), week(7d), month(30d) rolling windows
    periods = {"day": 86400, "week": 7*86400, "month": 30*86400}
    out = {k: 0.0 for k in periods}
    for r in rows:
        try:
            ts = int(r.get(ts_field) or 0)
        except Exception:
            continue
        for k, secs in periods.items():
            if ts and (now_ts - ts) <= secs:
                try:
                    if "amount" in r:
                        out[k] += float(r.get("amount") or 0)
                    elif "sum" in r:
                        out[k] += float(r.get("sum") or 0)
                except Exception:
                    pass
    return out

def _finance_snapshot() -> Dict[str, Dict[str, float]]:
    now_ts = int(time.time())
    invs = [i for i in (_read_json(INVOICES_FILE, []) or []) if isinstance(i, dict) and i.get("status") == "paid"]
    # revenue is paid invoices amount by paid_at
    rev_rows = [{"amount": float(i.get("amount") or 0), "paid_at": int(i.get("paid_at") or 0)} for i in invs]
    rev = _sum_by_period(rev_rows, "paid_at", now_ts)

    exp_rows = [{"amount": float(e.get("amount") or 0), "created_at": int(e.get("created_at") or 0)} for e in (_expense_rows() or []) if isinstance(e, dict)]
    exp = _sum_by_period(exp_rows, "created_at", now_ts)

    prof = {k: float(rev.get(k, 0.0)) - float(exp.get(k, 0.0)) for k in ("day", "week", "month")}
    return {"revenue": rev, "expenses": exp, "profit": prof}

async def admin_delete_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id):
        return ConversationHandler.END
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton('🗂 Удалить категорию', callback_data='admin_del_cat')],
        [InlineKeyboardButton('📦 Удалить товар', callback_data='admin_del_item')],
        [InlineKeyboardButton('⬅️ Назад', callback_data='admin')],
        [InlineKeyboardButton('❌ Выйти', callback_data='admin_cancel')],
    ])
    await q.message.reply_html('🗑 <b>Удаление</b>\n\nЧто удаляем?', reply_markup=kb)
    return ADMIN_DELETE_MENU

async def admin_del_cat_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id):
        return ConversationHandler.END
    data = load_catalog()
    cats = data.get('categories', [])
    if not cats:
        await q.message.reply_text('Категорий пока нет.')
        return ADMIN_MENU
    await q.message.reply_html('🗂 Выберите категорию для удаления:', reply_markup=_cat_buttons(cats, 'admin_del_cat_', 'admin_delete'))
    return ADMIN_DELETE_CAT_SELECT

async def admin_del_cat_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id):
        return ConversationHandler.END
    data = load_catalog()
    cats = data.get('categories', [])
    try:
        cidx = int(q.data.split('_')[-1])
    except Exception:
        return ADMIN_MENU
    if not (0 <= cidx < len(cats)):
        await q.message.reply_text('Категория не найдена.')
        return ADMIN_MENU
    context.user_data['admin_delete'] = {"target": "category", "cat_idx": cidx}
    title = cats[cidx].get("title", "Категория")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton('✅ Да, удалить', callback_data='admin_del_confirm')],
        [InlineKeyboardButton('❌ Отмена', callback_data='admin_delete')],
    ])
    await q.message.reply_html(f"⚠️ Удалить категорию <b>{title}</b>?\n\nВсе товары внутри тоже удалятся.", reply_markup=kb)
    return ADMIN_DELETE_CONFIRM

async def admin_del_item_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id):
        return ConversationHandler.END
    data = load_catalog()
    cats = data.get('categories', [])
    if not cats:
        await q.message.reply_text('Категорий пока нет.')
        return ADMIN_MENU
    await q.message.reply_html('📦 Выберите категорию:', reply_markup=_cat_buttons(cats, 'admin_del_item_cat_', 'admin_delete'))
    return ADMIN_DELETE_ITEM_CAT

async def admin_del_item_choose_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id):
        return ConversationHandler.END
    data = load_catalog()
    cats = data.get('categories', [])
    try:
        cidx = int(q.data.split('_')[-1])
    except Exception:
        return ADMIN_MENU
    if not (0 <= cidx < len(cats)):
        await q.message.reply_text('Категория не найдена.')
        return ADMIN_MENU
    cat = cats[cidx]
    items = cat.get("items", []) or []
    if not items:
        await q.message.reply_text('В этой категории нет товаров.')
        return ADMIN_DELETE_MENU
    rows = []
    for i, it in enumerate(items):
        rows.append([InlineKeyboardButton(it.get("title", f"Товар {i+1}"), callback_data=f"admin_del_item_{cidx}_{i}")])
    rows.append([InlineKeyboardButton('⬅️ Назад', callback_data='admin_delete')])
    await q.message.reply_html('📦 Выберите товар для удаления:', reply_markup=InlineKeyboardMarkup(rows))
    return ADMIN_DELETE_ITEM_SELECT

async def admin_del_item_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id):
        return ConversationHandler.END
    data = load_catalog()
    cats = data.get('categories', [])
    try:
        _, _, _, cidx_s, iidx_s = q.data.split('_')
        cidx = int(cidx_s); iidx = int(iidx_s)
    except Exception:
        return ADMIN_MENU
    if not (0 <= cidx < len(cats)):
        return ADMIN_MENU
    items = cats[cidx].get("items", []) or []
    if not (0 <= iidx < len(items)):
        return ADMIN_MENU
    context.user_data['admin_delete'] = {"target": "item", "cat_idx": cidx, "item_idx": iidx}
    title = items[iidx].get("title", "Товар")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton('✅ Да, удалить', callback_data='admin_del_confirm')],
        [InlineKeyboardButton('❌ Отмена', callback_data='admin_delete')],
    ])
    await q.message.reply_html(f"⚠️ Удалить товар <b>{title}</b>?", reply_markup=kb)
    return ADMIN_DELETE_CONFIRM

async def admin_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id):
        return ConversationHandler.END

    st = context.user_data.get("admin_delete") or {}
    tgt = st.get("target")
    data = load_catalog()
    cats = data.get("categories", [])

    if tgt == "category":
        cidx = int(st.get("cat_idx", -1))
        if 0 <= cidx < len(cats):
            title = cats[cidx].get("title", "Категория")
            del cats[cidx]
            data["categories"] = cats
            _write_json(CATALOG_PATH, data)
            await q.message.reply_html(f"✅ Категория <b>{title}</b> удалена.")
            return ADMIN_MENU

    if tgt == "item":
        cidx = int(st.get("cat_idx", -1))
        iidx = int(st.get("item_idx", -1))
        if 0 <= cidx < len(cats):
            items = cats[cidx].get("items", []) or []
            if 0 <= iidx < len(items):
                title = items[iidx].get("title", "Товар")
                del items[iidx]
                cats[cidx]["items"] = items
                _write_json(CATALOG_PATH, data)
                await q.message.reply_html(f"✅ Товар <b>{title}</b> удалён.")
                return ADMIN_MENU

    await q.message.reply_text("Не удалось удалить. Откройте /admin заново.")
    return ConversationHandler.END

async def admin_broadcast_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id):
        return ConversationHandler.END
    await q.message.reply_html("📣 <b>Рассылка</b>\n\nОтправьте текст рассылки одним сообщением.\nПоддерживается HTML (как в боте).")
    return ADMIN_BROADCAST_TEXT

async def admin_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_admin(uid):
        return ConversationHandler.END

    text = update.message.text or ""
    user_ids = get_all_user_ids()
    ok = 0; fail = 0
    for i, chat_id in enumerate(user_ids):
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            ok += 1
        except Exception:
            fail += 1
        # gentle rate limit
        if (i + 1) % 20 == 0:
            await asyncio.sleep(0.6)

    await update.message.reply_html(f"✅ Рассылка завершена.\n\nОтправлено: <b>{ok}</b>\nОшибки: <b>{fail}</b>")
    return ADMIN_MENU

async def admin_stats_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id):
        return ConversationHandler.END

    snap = _finance_snapshot()
    rev = snap["revenue"]; exp = snap["expenses"]; prof = snap["profit"]

    msg = (
        f"📊 <b>Финансы (rolling)</b>\n\n"
        f"💰 Выручка:\n• День: <b>{rev['day']:.2f} ₽</b>\n• Неделя: <b>{rev['week']:.2f} ₽</b>\n• Месяц: <b>{rev['month']:.2f} ₽</b>\n\n"
        f"🧾 Расходы:\n• День: <b>{exp['day']:.2f} ₽</b>\n• Неделя: <b>{exp['week']:.2f} ₽</b>\n• Месяц: <b>{exp['month']:.2f} ₽</b>\n\n"
        f"📈 Чистая прибыль:\n• День: <b>{prof['day']:.2f} ₽</b>\n• Неделя: <b>{prof['week']:.2f} ₽</b>\n• Месяц: <b>{prof['month']:.2f} ₽</b>"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton('➕ Добавить расход', callback_data='admin_exp_add')],
        [InlineKeyboardButton('⬅️ Назад', callback_data='admin')],
        [InlineKeyboardButton('❌ Выйти', callback_data='admin_cancel')],
    ])
    await q.message.reply_html(msg, reply_markup=kb)
    return ADMIN_STATS_MENU

async def admin_expense_add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id):
        return ConversationHandler.END
    await q.message.reply_html("🧾 Введите сумму расхода (например: <code>199</code> или <code>199.50</code>):")
    return ADMIN_EXPENSE_ADD_AMOUNT

async def admin_expense_add_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_admin(uid):
        return ConversationHandler.END

    raw = (update.message.text or "").strip().replace(",", ".")
    try:
        amount = float(raw)
        if amount <= 0:
            raise ValueError
    except Exception:
        await update.message.reply_text("Сумма должна быть положительным числом. Пример: 199 или 199.50")
        return ADMIN_EXPENSE_ADD_AMOUNT

    context.user_data["admin_exp_amount"] = float(amount)
    await update.message.reply_html("Добавьте комментарий/причину (или отправьте <code>skip</code>):")
    return ADMIN_EXPENSE_ADD_NOTE

async def admin_expense_add_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_admin(uid):
        return ConversationHandler.END

    note = (update.message.text or "").strip()
    if note.lower() == "skip":
        note = ""
    amount = float(context.user_data.get("admin_exp_amount") or 0)
    add_expense(amount, note)
    await update.message.reply_html("✅ Расход добавлен.")
    return ADMIN_MENU

# --------------------
# Admin descriptions (categories / items)
# --------------------

async def admin_desc_cat_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry: choose a category to view/edit its description."""
    q = update.callback_query
    if q:
        await q.answer()
        uid = q.from_user.id
    else:
        uid = update.effective_user.id if update.effective_user else 0
    if not _is_admin(uid):
        return ConversationHandler.END

    data = load_catalog()
    cats = data.get('categories', [])
    if not cats:
        await (q.message if q else update.message).reply_text('Категорий пока нет. Добавьте категорию в админке.')
        return ADMIN_MENU

    kb = _cat_buttons(cats, prefix='admin_desc_cat_', back_cb='admin_desc')
    await (q.message if q else update.message).reply_html('📝 <b>Описания категорий</b>\n\nВыберите категорию:', reply_markup=kb)
    return ADMIN_DESC_CAT_SELECT


async def admin_desc_item_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry: choose a category, then choose an item to view/edit its description."""
    q = update.callback_query
    if q:
        await q.answer()
        uid = q.from_user.id
    else:
        uid = update.effective_user.id if update.effective_user else 0
    if not _is_admin(uid):
        return ConversationHandler.END

    data = load_catalog()
    cats = data.get('categories', [])
    if not cats:
        await (q.message if q else update.message).reply_text('Категорий пока нет. Добавьте категорию в админке.')
        return ADMIN_MENU

    rows = []
    for i, c in enumerate(cats):
        rows.append([InlineKeyboardButton(c.get('title', f'Категория {i+1}'), callback_data=f"admin_desc_item_list_{i}")])
    rows.append([InlineKeyboardButton('⬅️ Назад', callback_data='admin_desc')])
    kb = InlineKeyboardMarkup(rows)
    await (q.message if q else update.message).reply_html('📝 <b>Описания товаров</b>\n\nСначала выберите категорию:', reply_markup=kb)
    return ADMIN_DESC_ITEM_SELECT


async def admin_desc_item_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """After choosing a category, show its items for description editing."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if not _is_admin(uid):
        return ConversationHandler.END

    try:
        cidx = int(q.data.split('_')[-1])
    except Exception:
        await q.message.reply_text('Ошибка выбора категории.')
        return ADMIN_MENU

    data = load_catalog()
    cats = data.get('categories', [])
    if cidx < 0 or cidx >= len(cats):
        await q.message.reply_text('Категория не найдена.')
        return ADMIN_MENU

    cat = cats[cidx]
    items = cat.get('items', []) or []
    if not items:
        await q.message.reply_text('В этой категории нет товаров.')
        return ADMIN_DESC_ITEM_SELECT

    kb = _item_buttons(cat, cidx, prefix='admin_desc_item_', back_cb='admin_desc_item')
    await q.message.reply_html(f"📝 <b>Описания товаров</b>\n\nКатегория: <b>{cat.get('title','Категория')}</b>\nВыберите товар:", reply_markup=kb)
    return ADMIN_DESC_ITEM_SELECT


async def admin_desc_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if not _is_admin(uid):
        return ConversationHandler.END
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton('🗂 Описание категории', callback_data='admin_desc_cat')],
        [InlineKeyboardButton('📦 Описание товара', callback_data='admin_desc_item')],
        [InlineKeyboardButton('⬅️ Назад', callback_data='admin')],
        [InlineKeyboardButton('❌ Выйти', callback_data='admin_cancel')],
    ])
    await q.message.reply_html('📝 <b>Описания</b>\n\nЧто редактируем?', reply_markup=kb)
    return ADMIN_MENU


async def admin_desc_edit_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if not _is_admin(uid):
        return ConversationHandler.END

    st = context.user_data.get('admin_desc') or {}
    tgt = st.get('target')
    if tgt not in ('category', 'item'):
        await q.message.reply_text('Не удалось определить объект. Откройте /admin заново.')
        return ConversationHandler.END

    if tgt == 'category':
        await q.message.reply_text('✏️ Введите новое описание категории одним сообщением:')
    else:
        await q.message.reply_text('✏️ Введите новое описание товара одним сообщением:')
    context.user_data['admin_desc_mode'] = 'edit'
    return ADMIN_DESC_INPUT


async def admin_desc_delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if not _is_admin(uid):
        return ConversationHandler.END

    st = context.user_data.get('admin_desc') or {}
    tgt = st.get('target')
    cidx = int(st.get('cat_idx', -1))
    iidx = int(st.get('item_idx', -1))

    data = load_catalog()
    cats = data.get('categories', [])
    if tgt == 'category' and 0 <= cidx < len(cats):
        cats[cidx]['description'] = ''
        _write_json(CATALOG_PATH, data)
        await q.message.reply_text('🗑 Описание категории удалено.')
        return ADMIN_MENU

    if tgt == 'item' and 0 <= cidx < len(cats):
        items = cats[cidx].get('items', []) or []
        if 0 <= iidx < len(items):
            items[iidx]['description'] = ''
            _write_json(CATALOG_PATH, data)
            await q.message.reply_text('🗑 Описание товара удалено.')
            return ADMIN_MENU

    await q.message.reply_text('Не удалось удалить описание. Откройте /admin заново.')
    return ConversationHandler.END


async def admin_desc_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_admin(uid):
        return ConversationHandler.END

    desc = (update.message.text or '').strip()
    st = context.user_data.get('admin_desc') or {}
    tgt = st.get('target')
    cidx = int(st.get('cat_idx', -1))
    iidx = int(st.get('item_idx', -1))

    data = load_catalog()
    cats = data.get('categories', [])

    if tgt == 'category' and 0 <= cidx < len(cats):
        cats[cidx]['description'] = desc
        _write_json(CATALOG_PATH, data)
        await update.message.reply_text('✅ Описание категории обновлено.')
        return ADMIN_MENU

    if tgt == 'item' and 0 <= cidx < len(cats):
        items = cats[cidx].get('items', []) or []
        if 0 <= iidx < len(items):
            items[iidx]['description'] = desc
            _write_json(CATALOG_PATH, data)
            await update.message.reply_text('✅ Описание товара обновлено.')
            return ADMIN_MENU

    await update.message.reply_text('Не удалось обновить описание. Откройте /admin заново.')
    return ConversationHandler.END


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
    if unit == "package":
        return f"{p:.0f} ₽ пакет"
    tail = "за 1000" if unit=="per_1000" else "за 100"
    return f"{p:.2f} ₽ {tail}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Добро пожаловать в <b>BoostX</b> — платформу профессионального продвижения.\n\n"
        "Мы помогаем развивать <b>Telegram</b>, <b>YouTube</b> и <b>TikTok</b> "
        "с быстрыми и надёжными результатами.\n\n"
        "Откройте каталог, чтобы выбрать услугу, или воспользуйтесь кнопками ниже "
        "для управления балансом и связи с поддержкой."
        "\n\n🗒️Оферта - https://teletype.in/@boostx/ofertaboostx"
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
    remember_user(update.effective_user.id)

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
        parse_mode=ParseMode.HTML,
		disable_web_page_preview=True
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📘 Команды:\n"
        "/start — приветствие\n"
        "/catalog — каталог услуг\n"
        "/balance — баланс\n"
        "/topup &lt;сумма&gt; — пополнить баланс\n"
        "/admin — админ-панель (только админ)\n"
        "/confirm_payment &lt;invoice_id&gt; — подтверждение оплаты (админ)\n"
    )
    await update.message.reply_html(text)

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_html(f"💳 <b>Ваш баланс:</b> <code>{get_balance(uid):.2f} ₽</code>")


async def promo_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    # Ввод промокода из профиля (сохраняем для следующего заказа)
    context.user_data["awaiting_promo_profile"] = True
    await q.message.reply_text("🎟 Введите промокод одним сообщением:")

async def promo_profile_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_promo_profile"):
        return
    context.user_data["awaiting_promo_profile"] = False
    code = (update.message.text or "").strip().upper()
    promos = _load_promo_codes()
    cfg = promos.get(code)
    if not cfg or not cfg.get("active", True):
        await update.message.reply_text("Промокод не найден или не активен.")
        return
    if promo_is_used(update.effective_user.id, code):
        await update.message.reply_text("Этот промокод уже использован вами.")
        return
    context.user_data["active_promo"] = code
    await update.message.reply_html(f"✅ Промокод <code>{code}</code> применён. Скидка учтётся при следующем оформлении заказа (от 100 ₽).")

async def promo_order_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    # Ввод промокода на этапе подтверждения заказа
    context.user_data["awaiting_promo_order"] = True
    await q.message.reply_text("🎟 Введите промокод одним сообщением:")

async def promo_order_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_promo_order"):
        return ConversationHandler.END
    context.user_data["awaiting_promo_order"] = False
    info = context.user_data.get("order")
    if not info:
        await update.message.reply_text("Заказ не найден. Откройте каталог и выберите услугу заново.")
        return ConversationHandler.END
    if info.get("type") == "combo":
        await update.message.reply_text("Промокод не применяется к комбо-наборам.")
        return CONFIRM
    code = (update.message.text or "").strip().upper()
    base_cost = float(info.get("base_cost") or info.get("cost") or 0)
    # если ранее применяли скидку — пересчитаем от base_cost
    if base_cost <= 0:
        base_cost = float(info.get("cost") or 0)
    ok, msg, percent = promo_validate(code, base_cost, update.effective_user.id, allow_for_combo=False)
    if not ok:
        await update.message.reply_text(msg or "Промокод не подходит.")
        return CONFIRM
    context.user_data["active_promo"] = code
    info["promo_code"] = code
    info["promo_percent"] = int(percent)
    info["base_cost"] = base_cost
    new_cost = apply_discount(base_cost, int(percent))
    info["cost"] = float(new_cost)
    context.user_data["order"] = info

    bal = get_balance(update.effective_user.id)
    promo_line = f"• Промокод: <code>{code}</code> (−{int(percent)}%)\n"
    text = (
        "✅ <b>Подтверждение заказа</b>\n\n"
        f"• Услуга: <b>{info['title']}</b>\n"
        f"• Кол-во: <code>{info['qty']}</code>\n"
        f"• Ссылка: <code>{info['link']}</code>\n"
        f"• Стоимость: <code>{float(new_cost):.2f} ₽</code>\n"
        f"{promo_line}"
        f"• Баланс: <code>{bal:.2f} ₽</code>\n\n"
        "Подтвердить оформление?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎟 Промокод", callback_data="promo_order")],
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_order")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_order")],
    ])
    await update.message.reply_html(text, reply_markup=kb)
    return CONFIRM

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
        [InlineKeyboardButton("🎟 Промокод", callback_data="promo")],
        [InlineKeyboardButton("🆘 Поддержка", callback_data="support")],
    ])
    await q.message.reply_html(text, reply_markup=kb)


async def unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Safety net: always answer unknown callback queries to avoid endless "loading" in Telegram UI."""
    q = update.callback_query
    if not q:
        return
    try:
        await q.answer("Меню обновилось. Если кнопка не сработала — нажмите /start или откройте Каталог заново.")
    except Exception:
        # Ignore any errors here; this handler exists only to stop the loading spinner.
        pass

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
    desc = (cat.get('description') or '').strip()
    header = f"<b>{title}</b>" + (f"\n\n{desc}" if desc else '')
    await q.message.reply_html(f"{header}\nВыберите услугу:", reply_markup=InlineKeyboardMarkup(rows))

LINK, QTY, CONFIRM, PROMO = range(4)

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
        "item_id": item.get("id"),
        "title": item.get("title","Услуга"),
        "price": float(item.get("price",0)),
        "item_type": item.get("type","single"),
        "platform": item.get("platform", cat.get("title","Категория")),
        "components": item.get("components", []),
        "discount_percent": int(item.get("discount_percent", 0)),
        "supplier_service_id": item.get("service_id"),
        "description": (item.get("description") or "").strip(),
    }
    # Если это комбо-набор — показываем состав до ввода ссылки
    if context.user_data["order"].get("item_type") == "combo":
        o = context.user_data["order"]
        comps = o.get("components", []) or []
        lines = [f"🎁 Вы выбрали: {o.get('title','Комбо-набор')}", "", "📦 Состав набора:"]
        for c in comps:
            c_title = c.get("title", "Услуга")
            c_qty = c.get("qty", "")
            lines.append(f"• {c_title} — {c_qty}")
        cost_preview = float(compute_cost(float(o.get("price", 0)), o.get("unit","package"), float(o.get("mult",1.0)), 1))
        uid = update.effective_user.id
        bal = get_balance(uid)
        disc = int(o.get("discount_percent", 0))
        if disc:
            lines.append("")
            lines.append(f"✅ Выгода: -{disc}% уже учтена")
        lines.append(f"💰 Стоимость пакета: {cost_preview:.0f} ₽")
        lines.append(f"👛 Ваш баланс: {bal:.2f} ₽")
        await q.message.reply_text("\n".join(lines))

    # Показать описание услуги (если есть)
    if context.user_data["order"].get("description") and context.user_data["order"].get("item_type") != "combo":
        o = context.user_data["order"]
        cost_preview = compute_cost(float(o.get("price", 0)), o.get("unit", "per_1000"), float(o.get("mult", 1.0)), 1000 if o.get("unit") != "package" else 1)
        # Для package preview уже в комбо, поэтому тут только single
        await q.message.reply_html(
            f"ℹ️ <b>{o.get('title','Услуга')}</b>\n\n{ o.get('description','') }\n\nЦена: <b>{price_str(o.get('price',0), o.get('unit','per_1000'), o.get('mult',1.0))}</b>",
            disable_web_page_preview=True,
        )

    await q.message.reply_text("🔗 Отправьте ссылку (URL), на которую оформляем заказ:")
    return LINK

async def order_get_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = (update.message.text or "").strip()
    if not (link.startswith("http://") or link.startswith("https://") or ".com" in link or ".ru" in link):
        await update.message.reply_text("Похоже, это не ссылка. Отправьте корректный URL:")
        return LINK

    info = context.user_data.get("order", {})
    info["link"] = link

    # Комбо-набор: количество фиксированное, сразу подтверждение
    if info.get("item_type") == "combo":
        cost = float(compute_cost(info.get("price",0), info.get("unit","package"), info.get("mult",1.0), 1))
        uid = update.effective_user.id
        bal = get_balance(uid)
        if bal < cost:
            await update.message.reply_text(
                f"""❌ Недостаточно средств для оплаты

Стоимость: {cost:.0f} ₽
Ваш баланс: {bal:.2f} ₽

💳 Пополните баланс командой: /topup сумма"""
            )
            context.user_data.pop("order", None)
            return ConversationHandler.END

        info["cost"] = cost
        comps = info.get("components", []) or []
        comp_text = "\n".join([f"• {c.get('title','')} — <code>{int(c.get('qty',0))}</code>" for c in comps])
        text = (
            "✅ <b>Подтверждение заказа</b>\n\n"
            f"• Пакет: <code>{info.get('title','КОМБО')}</code>\n"
            "• Состав:\n"
            f"{comp_text}\n\n"
            f"• Ссылка: <code>{link}</code>\n"
            f"• Стоимость: <code>{cost:.0f} ₽</code>\n"
            f"• Баланс: <code>{bal:.2f} ₽</code>\n\n"
            "Подтвердить оформление?"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_order")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_order")],
        ])
        await update.message.reply_html(text, reply_markup=kb)
        return CONFIRM

    # Обычный товар
    await update.message.reply_text("🔢 Укажите количество (целое число):")
    return QTY

def compute_cost(price: float, unit: str, mult: float, qty: int) -> float:
    if unit == "package":
        return float(price) * float(mult)
    base = 1000.0 if unit=="per_1000" else 100.0
    return float(price) * float(mult) * (qty / base)

def resolve_service_id(cat_title: str, item_title: str, item_id: str | None = None) -> int|None:
    m = load_map()

    # Preferred: lookup by internal item id/code (stable even if titles/categories change)
    if item_id:
        sid = m.get(str(item_id).strip())
        if sid is not None:
            return int(sid)

    # Legacy: exact match by category + item title
    sid = m.get(f"{cat_title}:::{item_title}")
    if sid is not None:
        return int(sid)

    # Legacy fallback: match by item title only
    needle = f":::{(item_title or '').strip()}"
    for k, v in m.items():
        if isinstance(k, str) and k.endswith(needle):
            try:
                return int(v)
            except Exception:
                return None
    return None

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
    sid = info.get('supplier_service_id') or resolve_service_id(info.get("cat_title","Категория"), info.get("title","Услуга"), info.get("item_id"))
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
    # Промокод (скидка %), применяется только к обычным услугам (не к комбо)
    promo = context.user_data.get("active_promo")
    if promo and float(cost) >= 100:
        ok, msg, percent = promo_validate(str(promo), float(cost), int(uid), allow_for_combo=False)
        if ok and percent:
            info["promo_code"] = str(promo).upper()
            info["promo_percent"] = int(percent)
            info["base_cost"] = float(cost)
            cost = apply_discount(float(cost), int(percent))
        else:
            # если промокод не подходит — сбрасываем
            context.user_data.pop("active_promo", None)
            info.pop("promo_code", None); info.pop("promo_percent", None); info.pop("base_cost", None)
    bal = get_balance(uid)
    if bal < cost:
        await update.message.reply_text(
                f"""❌ Недостаточно средств для оплаты

Стоимость: {cost:.0f} ₽
Ваш баланс: {bal:.2f} ₽

💳 Пополните баланс командой: /topup сумма"""
        )
        context.user_data.pop("order", None)
        return ConversationHandler.END

    info["service_id"] = int(sid)
    info["qty"] = int(qty)
    info["cost"] = float(cost)
    context.user_data["order"] = info

    promo_line = ""
    if info.get("promo_code") and info.get("promo_percent"):
        promo_line = f"• Промокод: <code>{info.get('promo_code')}</code> (−{int(info.get('promo_percent'))}%)\n"
    text = (
        "✅ <b>Подтверждение заказа</b>\n\n"
        f"• Услуга: <code>{info.get('title','Услуга')}</code>\n"
        f"• Кол-во: <code>{qty}</code>\n"
        f"• Ссылка: <code>{info.get('link','')}</code>\n"
        f"• Стоимость: <code>{cost:.2f} ₽</code>\n"
        f"{promo_line}"
        f"• Баланс: <code>{bal:.2f} ₽</code>\n\n"
        "Подтвердить оформление?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎟 Промокод", callback_data="promo_order")],
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

    # Комбо-набор: создаём несколько заказов поставщику, списание один раз
    if info.get("item_type") == "combo":
        link = info.get("link", "")
        cost = float(info.get("cost", 0.0))
        comps = info.get("components", []) or []
        if not link or not comps or cost <= 0:
            await q.message.reply_text("Данные комбо-заказа не найдены. Откройте каталог и оформите заказ заново.")
            context.user_data.pop("order", None)
            return ConversationHandler.END

        bal = get_balance(uid)
        if bal < cost:
            await q.message.reply_html(
                f"Недостаточно средств. Нужно <code>{cost:.0f} ₽</code>, на балансе <code>{bal:.2f} ₽</code>."
            )
            context.user_data.pop("order", None)
            return ConversationHandler.END

        # списываем перед созданием
        set_balance(uid, bal - cost)

        provider_rows = []
        try:
            for c in comps:
                sid = int(c.get("service_id", 0))
                qty = int(c.get("qty", 0))
                if sid <= 0 or qty <= 0:
                    raise RuntimeError(f"Bad component: {c}")
                res = await asyncio.to_thread(looksmm_add, sid, link, qty)
                if isinstance(res, dict):
                    provider_order_id = res.get("order")
                else:
                    provider_order_id = None
                if not provider_order_id:
                    raise RuntimeError(f"LooksMM response: {res}")
                provider_rows.append({
                    "service_id": sid,
                    "qty": qty,
                    "provider_order_id": provider_order_id,
                })

            order_id = str(uuid.uuid4())[:8]
            append_order({
                "order_id": order_id,
                "user_id": uid,
                "username": q.from_user.username or "",
                "title": info.get("title", "КОМБО"),
                "type": "combo",
                "cost": cost,
                "link": link,
                "items": provider_rows,
            })

            # уведомление админу
            try:
                lines = "\n".join([f"{r['service_id']} x {r['qty']} -> {r['provider_order_id']}" for r in provider_rows])
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        "🆕 Новый КОМБО-заказ\n\n"
                        f"User: {uid} (@{q.from_user.username or '-'})\n"
                        f"Пакет: {info.get('title','КОМБО')}\n"
                        f"cost: {cost:.0f} ₽\n"
                        f"link: {link}\n\n"
                        f"{lines}\n"
                        f"order_id: {order_id}"
                    )
                )
            except Exception:
                pass

            # статус-экран
            items_txt = "\n".join([
                f"• <code>{r['service_id']}</code> × <code>{r['qty']}</code> → <code>{r['provider_order_id']}</code>" for r in provider_rows
            ])
            status_text = (
                "✅ <b>Комбо-заказ создан</b>\n\n"
                f"• Пакет: <code>{info.get('title','КОМБО')}</code>\n"
                f"• Ссылка: <code>{link}</code>\n"
                f"• Списано: <code>{cost:.0f} ₽</code>\n"
                f"• Order ID: <code>{order_id}</code>\n\n"
                "• Заказы поставщика:\n"
                f"{items_txt}"
            )
            status_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("👤 Профиль", callback_data="profile"), InlineKeyboardButton("📋 Каталог", callback_data="catalog")],
                [InlineKeyboardButton("🆘 Поддержка", callback_data="support")],
            ])
            await q.message.reply_html(status_text, reply_markup=status_kb)
        except Exception as e:
            set_balance(uid, bal)
            await q.message.reply_text(f"Ошибка создания комбо-заказа: {e}")

        context.user_data.pop("order", None)
        return ConversationHandler.END

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
        append_order({
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
    app.add_handler(CallbackQueryHandler(promo_cb, pattern="^promo$"))
    app.add_handler(CallbackQueryHandler(promo_order_cb, pattern="^promo_order$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, promo_profile_input, block=False), group=1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, promo_order_input, block=False), group=1)

    # Оформление заказов
    conv_order = ConversationHandler(
        entry_points=[CallbackQueryHandler(order_entry, pattern="^item_")],
        states={
            0: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_get_link)],
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_get_qty)],
            2: [CallbackQueryHandler(order_confirm, pattern="^confirm_order$"), CallbackQueryHandler(order_cancel_cb, pattern="^cancel_order$")],
        },
        fallbacks=[CommandHandler("cancel", order_cancel)],
        allow_reentry=True,
        per_message=False,
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
        allow_reentry=True,
        per_message=False,
        name="support_conv",
        persistent=False,
    )

    app.add_handler(conv_support)

    # Админ-панель (цены / категории / товары / описания)
    conv_admin = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start), CallbackQueryHandler(admin_menu_cb, pattern="^admin$")],
        states={
            ADMIN_MENU: [
                CallbackQueryHandler(admin_price_entry, pattern="^admin_price$"),
                CallbackQueryHandler(admin_add_cat_entry, pattern="^admin_add_cat$"),
                CallbackQueryHandler(admin_add_item_entry, pattern="^admin_add_item$"),
                CallbackQueryHandler(admin_delete_entry, pattern="^admin_delete$"),
                CallbackQueryHandler(admin_broadcast_entry, pattern="^admin_broadcast$"),
                CallbackQueryHandler(admin_stats_entry, pattern="^admin_stats$"),
                CallbackQueryHandler(admin_desc_menu_cb, pattern="^admin_desc$"),
                CallbackQueryHandler(admin_desc_cat_entry, pattern="^admin_desc_cat$"),
                CallbackQueryHandler(admin_desc_item_entry, pattern="^admin_desc_item$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
            ],

            # Price edit
            ADMIN_SELECT_CAT: [
                CallbackQueryHandler(admin_choose_cat, pattern=r"^admin_cat_"),
                CallbackQueryHandler(admin_price_entry, pattern="^admin_price$"),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            ADMIN_SELECT_ITEM: [
                CallbackQueryHandler(admin_choose_item, pattern=r"^admin_item_"),
                CallbackQueryHandler(admin_choose_cat, pattern=r"^admin_cat_"),
                CallbackQueryHandler(admin_price_entry, pattern="^admin_price$"),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            ADMIN_PRICE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_price_input),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
            ],

            # Add category
            ADMIN_ADD_CAT_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_cat_title),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],

            # Add item flow
            ADMIN_ADD_ITEM_CAT: [
                CallbackQueryHandler(admin_add_item_choose_cat, pattern=r"^admin_add_item_cat_"),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            ADMIN_ADD_ITEM_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_item_title),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            ADMIN_ADD_ITEM_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_item_price),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],

            ADMIN_ADD_ITEM_SUPPLIER: [
                CallbackQueryHandler(admin_add_item_supplier_choose, pattern=r"^admin_add_item_supplier_"),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            ADMIN_ADD_ITEM_SID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_item_sid),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            ADMIN_ADD_ITEM_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_item_desc),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],


            # Delete / Broadcast / Finance
            ADMIN_DELETE_MENU: [
                CallbackQueryHandler(admin_del_cat_entry, pattern="^admin_del_cat$"),
                CallbackQueryHandler(admin_del_item_entry, pattern="^admin_del_item$"),
                CallbackQueryHandler(admin_delete_entry, pattern="^admin_delete$"),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            ADMIN_DELETE_CAT_SELECT: [
                CallbackQueryHandler(admin_del_cat_choose, pattern=r"^admin_del_cat_"),
                CallbackQueryHandler(admin_delete_entry, pattern="^admin_delete$"),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            ADMIN_DELETE_ITEM_CAT: [
                CallbackQueryHandler(admin_del_item_choose_cat, pattern=r"^admin_del_item_cat_"),
                CallbackQueryHandler(admin_delete_entry, pattern="^admin_delete$"),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            ADMIN_DELETE_ITEM_SELECT: [
                CallbackQueryHandler(admin_del_item_choose, pattern=r"^admin_del_item_\d+_\d+$"),
                CallbackQueryHandler(admin_delete_entry, pattern="^admin_delete$"),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            ADMIN_DELETE_CONFIRM: [
                CallbackQueryHandler(admin_delete_confirm, pattern="^admin_del_confirm$"),
                CallbackQueryHandler(admin_delete_entry, pattern="^admin_delete$"),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            ADMIN_BROADCAST_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_text),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            ADMIN_STATS_MENU: [
                CallbackQueryHandler(admin_expense_add_entry, pattern="^admin_exp_add$"),
                CallbackQueryHandler(admin_stats_entry, pattern="^admin_stats$"),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            ADMIN_EXPENSE_ADD_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_expense_add_amount),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            ADMIN_EXPENSE_ADD_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_expense_add_note),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            # Descriptions
            ADMIN_DESC_MENU: [
                CallbackQueryHandler(admin_desc_edit_cb, pattern="^admin_desc_edit$"),
                CallbackQueryHandler(admin_desc_delete_cb, pattern="^admin_desc_delete$"),
                CallbackQueryHandler(admin_desc_menu_cb, pattern="^admin_desc$"),
                CallbackQueryHandler(admin_desc_cat_entry, pattern="^admin_desc_cat$"),
                CallbackQueryHandler(admin_desc_item_entry, pattern="^admin_desc_item$"),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
                # selection callbacks are routed through admin_choose_cat/item
                CallbackQueryHandler(admin_choose_cat, pattern=r"^admin_desc_cat_"),
                CallbackQueryHandler(admin_choose_item, pattern=r"^admin_desc_item_"),
                CallbackQueryHandler(admin_desc_item_list, pattern=r"^admin_desc_item_list_"),
            ],
            ADMIN_DESC_CAT_SELECT: [
                CallbackQueryHandler(admin_choose_cat, pattern=r"^admin_desc_cat_"),
                CallbackQueryHandler(admin_desc_cat_entry, pattern="^admin_desc_cat$"),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            ADMIN_DESC_ITEM_SELECT: [
                CallbackQueryHandler(admin_choose_item, pattern=r"^admin_desc_item_"),
                CallbackQueryHandler(admin_desc_item_list, pattern=r"^admin_desc_item_list_"),
                CallbackQueryHandler(admin_desc_item_entry, pattern="^admin_desc_item$"),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
            ADMIN_DESC_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_desc_input),
                CallbackQueryHandler(admin_menu_cb, pattern="^admin$"),
                CallbackQueryHandler(admin_cancel_cb, pattern="^admin_cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel_cmd)],
        allow_reentry=True,
        per_message=False,
        name="admin_conv",
        persistent=False,
    )
    app.add_handler(conv_admin)

    # Safety net: answer any unexpected callback to stop Telegram "loading" spinner
    app.add_handler(CallbackQueryHandler(unknown_callback))

    return app

if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set")
    print("🚀 Bot is running...")
    application = build_application()
    application.run_polling(drop_pending_updates=True)
