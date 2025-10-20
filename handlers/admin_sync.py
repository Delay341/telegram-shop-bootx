
import difflib, asyncio, os, json
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from boostx_ext.looksmm import services
from boostx_ext.mapper import load_map, save_map, title_key, norm

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CATALOG_PATH = Path("config/config.json")

def register_admin_handlers(app: Application):
    app.add_handler(CommandHandler("sync_services", cmd_sync_services))
    app.add_handler(CommandHandler("set_service", cmd_set_service))
    app.add_handler(CommandHandler("show_map", cmd_show_map))
    app.add_handler(CommandHandler("show_unmapped", cmd_show_unmapped))

def _iter_price_items():
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    for ci, cat in enumerate(data.get("categories", [])):
        ctitle = cat.get("title", "")
        unit = cat.get("unit", "per_1000")
        for ii, item in enumerate(cat.get("items", [])):
            yield ci, ii, ctitle, unit, item

async def cmd_show_map(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    m = load_map()
    total = len(m)
    args = context.args or []
    show_all = (len(args) >= 1 and args[0].lower() in ("all", "все"))
    lines = [f"- {k} -> {v}" for k, v in m.items()]
    header = f"Текущая карта соответствий: всего {total}\n"
    if not lines:
        await update.message.reply_text(header + "Пока пусто.")
        return
    if show_all:
        chunk = 80
        await update.message.reply_text(header + "(полный список)")
        for i in range(0, len(lines), chunk):
            await update.message.reply_text("\n".join(lines[i:i+chunk]))
    else:
        await update.message.reply_text(header + "Первые 50:\n" + "\n".join(lines[:50]) + (\
            "\n… (используй /show_map all для полного списка)" if total > 50 else ""))

async def cmd_show_unmapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    m = load_map()
    unmapped = []
    for ci, ii, ctitle, unit, item in _iter_price_items():
        key = title_key(ctitle, item.get("title",""))
        if item.get("service_id"):
            continue
        if key in m:
            continue
        unmapped.append(f"[{ci}:{ii}] {ctitle} — {item.get('title','')}")
    total = len(unmapped)
    if total == 0:
        await update.message.reply_text("Все позиции прайса привязаны (либо заданы вручную, либо в карте соответствий).")
        return
    await update.message.reply_text(f"Непривязанных позиций: {total}. Показываю первые 100:")
    await update.message.reply_text("\n".join(unmapped[:100]) + (\
        "\n… (сузь прайс или используй ручную привязку /set_service)" if total > 100 else ""))

async def cmd_set_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if len(context.args) < 3:
        await update.message.reply_html("Использование: <code>/set_service &lt;cat_index&gt; &lt;item_index&gt; &lt;service_id&gt;</code>")
        return
    try:
        cidx = int(context.args[0]); iidx = int(context.args[1]); sid = int(context.args[2])
    except Exception:
        await update.message.reply_text("Индексы/ID должны быть числами.")
        return
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    cat = data["categories"][cidx]; item = cat["items"][iidx]
    key = title_key(cat["title"], item["title"])
    m = load_map(); m[key] = sid; save_map(m)
    await update.message.reply_text(f"OK, сохранено: {key} -> {sid}")

async def cmd_sync_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        threshold = float(context.args[0]) if context.args else 0.60
        if threshold < 0 or threshold > 1: threshold = 0.60
    except Exception:
        threshold = 0.60

    await update.message.reply_text(f"⏳ Синхронизирую услуги с LookSMM… (threshold={threshold:.2f})")
    raw = await asyncio.to_thread(services)
    if not isinstance(raw, list):
        await update.message.reply_text("Неожиданный формат ответа поставщика.")
        return
    provider = [(str(it.get('service') or it.get('id')), str(it.get('name') or it.get('title') or '')) for it in raw]
    norm_list = [(sid, norm(name)) for sid, name in provider]

    m = load_map()
    total_in_price = 0
    already = 0
    mapped_now = 0
    left = 0

    for ci, ii, ctitle, unit, item in _iter_price_items():
        total_in_price += 1
        key = title_key(ctitle, item.get("title",""))
        if item.get("service_id"):
            already += 1; continue
        if key in m:
            already += 1; continue
        query = norm(item.get("title",""))
        best_sid, best_score = None, 0.0
        for sid, nm in norm_list:
            import difflib as _d
            score = _d.SequenceMatcher(None, query, nm).ratio()
            if score > best_score:
                best_score, best_sid = score, sid
        if best_sid and best_score >= threshold:
            m[key] = int(best_sid); mapped_now += 1
        else:
            left += 1

    save_map(m)
    await update.message.reply_text(
        "✅ Готово.\n"
        f"Всего позиций в прайсе: {total_in_price}\n"
        f"Уже привязаны: {already}\n"
        f"Привязано сейчас: {mapped_now}\n"
        f"Остались без привязки: {left}\n\n"
        "Карта: /show_map all\n"
        "Непривязанные: /show_unmapped\n"
        "Ручная привязка: /set_service <cat_index> <item_index> <service_id>"
    )
