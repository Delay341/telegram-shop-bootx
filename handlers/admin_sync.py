
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

async def cmd_show_map(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    m = load_map()
    text = "\n".join([f"- {k} -> {v}" for k, v in m.items()]) or "Пока пусто."
    await update.message.reply_text("Текущая карта соответствий (первые 50):\n" + "\n".join(text.splitlines()[:50]))

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
    await update.message.reply_text("⏳ Синхронизирую список услуг с LookSMM...")
    raw = await asyncio.to_thread(services)
    if not isinstance(raw, list):
        await update.message.reply_text("Неожиданный формат ответа поставщика.")
        return
    provider = [(str(it.get("service") or it.get("id")), str(it.get("name") or it.get("title") or "")) for it in raw]
    norm_list = [(sid, norm(name)) for sid, name in provider]

    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    m = load_map()
    created = 0
    for ci, cat in enumerate(data.get("categories", [])):
        ctitle = cat.get("title", "")
        for ii, item in enumerate(cat.get("items", [])):
            if item.get("service_id"):
                continue
            key = title_key(ctitle, item.get("title", ""))
            if key in m:
                continue
            query = norm(item.get("title",""))
            best_sid, best_score = None, 0.0
            for sid, nm in norm_list:
                score = difflib.SequenceMatcher(None, query, nm).ratio()
                if score > best_score:
                    best_score = score
                    best_sid = sid
            if best_sid and best_score >= 0.60:
                m[key] = int(best_sid); created += 1
    save_map(m)
    await update.message.reply_text(f"Готово. Добавлено соответствий: {created}. Команда /show_map покажет результат.")
