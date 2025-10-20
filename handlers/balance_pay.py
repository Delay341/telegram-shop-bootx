import json
import os
from pathlib import Path
from datetime import datetime
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
import aiohttp

BALANCES_FILE = Path(os.getenv("BALANCES_FILE", "balances.json"))
INVOICES_FILE = Path(os.getenv("INVOICES_FILE", "invoices.json"))
LOOKSMM_KEY = os.getenv("LOOKSMM_KEY")
PAY_INSTRUCTIONS = os.getenv("PAY_INSTRUCTIONS","В сообщение к переведу укажите: Ваш @username, услугу, количество")
CARD_DETAILS = os.getenv("CARD_DETAILS","https://www.tinkoff.ru/rm/r_nIutIhQtbX.tRouMxMcdC/kgUL962390")

def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    balances = load_json(BALANCES_FILE, {})
    balance = balances.get(user_id, 0)
    await update.message.reply_text(f"💰 Ваш баланс: {balance}₽")

async def cmd_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Использование: /topup <сумма>")
        return
    amount = int(context.args[0])
    user_id = str(update.effective_user.id)
    invoices = load_json(INVOICES_FILE, {})
    invoice_id = str(len(invoices) + 1)
    invoices[invoice_id] = {"user_id": user_id, "amount": amount, "status": "pending", "created_at": datetime.utcnow().isoformat()}
    save_json(INVOICES_FILE, invoices)
    text = (f"🧾 Счёт #{invoice_id} на сумму {amount}₽ создан.\n\n"
            f"💳 Оплатите по ссылке: <a href=\"{CARD_DETAILS}\">{CARD_DETAILS}</a>\n\n"
            f"{PAY_INSTRUCTIONS}\n\n"
            f"После оплаты администратор подтвердит платёж вручную.")
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_id = int(os.getenv("ADMIN_ID", "0"))
    if user_id != admin_id:
        await update.message.reply_text("⛔ Только админ может подтверждать оплату.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Использование: /confirm_payment <invoice_id>")
        return
    invoice_id = context.args[0]
    invoices = load_json(INVOICES_FILE, {})
    invoice = invoices.get(invoice_id)
    if not invoice:
        await update.message.reply_text("Счёт не найден.")
        return
    if invoice["status"] == "paid":
        await update.message.reply_text("Счёт уже был подтверждён ранее.")
        return
    balances = load_json(BALANCES_FILE, {})
    uid = invoice["user_id"]
    balances[uid] = balances.get(uid, 0) + invoice["amount"]
    invoice["status"] = "paid"
    save_json(INVOICES_FILE, invoices)
    save_json(BALANCES_FILE, balances)
    await update.message.reply_text(f"✅ Счёт #{invoice_id} подтверждён. Баланс пополнен.")
    try:
        await context.bot.send_message(chat_id=int(uid), text=f"✅ Ваш платёж #{invoice_id} на сумму {invoice['amount']}₽ подтверждён. Баланс пополнен!")
    except Exception:
        pass

async def looksmm_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not LOOKSMM_KEY:
        await update.message.reply_text("LOOKSMM_KEY не настроен.")
        return
    url = f"https://looksmm.ru/api/v2?action=services&key={LOOKSMM_KEY}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
    except Exception as e:
        await update.message.reply_text(f"Ошибка API: {e}")
        return
    if isinstance(data, list) and data:
        preview = "\n".join(f"{s['service']}: {s['name']} — {s['rate']}₽ / {s['min']}–{s['max']}" for s in data[:10])
        await update.message.reply_text(f"📋 Топ услуг LookSMM:\n\n{preview}")
    else:
        await update.message.reply_text("Не удалось получить список услуг.")

async def looksmm_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text("Использование: /buy <service_id> <link> <quantity>")
        return
    service_id, link, qty = context.args[0], context.args[1], context.args[2]
    user_id = str(update.effective_user.id)
    balances = load_json(BALANCES_FILE, {})
    balance = balances.get(user_id, 0)
    if not LOOKSMM_KEY:
        await update.message.reply_text("LOOKSMM_KEY не настроен.")
        return
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"https://looksmm.ru/api/v2?action=services&key={LOOKSMM_KEY}") as resp:
                services = await resp.json()
        except Exception as e:
            await update.message.reply_text(f"Ошибка при запросе услуг: {e}")
            return
    service = next((s for s in services if str(s["service"]) == service_id), None)
    if not service:
        await update.message.reply_text("Услуга не найдена.")
        return
    rate = float(service["rate"]); total = rate * float(qty) / 1000
    if balance < total:
        await update.message.reply_text(f"Недостаточно средств. Нужно {total:.2f}₽, на балансе {balance}₽.")
        return
    url = f"https://looksmm.ru/api/v2?action=add&service={service_id}&link={link}&quantity={qty}&key={LOOKSMM_KEY}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
                result = await resp.json()
        except Exception as e:
            await update.message.reply_text(f"Ошибка при создании заказа: {e}")
            return
    if "order" in result:
        balances[user_id] = balance - total
        save_json(BALANCES_FILE, balances)
        await update.message.reply_text(f"✅ Заказ #{result['order']} создан.\nСписано {total:.2f}₽.\nОстаток: {balances[user_id]:.2f}₽")
    else:
        await update.message.reply_text(f"Ошибка при создании заказа: {result}")

def register_balance_handlers(app):
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("topup", cmd_topup))
    app.add_handler(CommandHandler("confirm_payment", cmd_confirm))
    app.add_handler(CommandHandler("services", looksmm_services))
    app.add_handler(CommandHandler("buy", looksmm_buy))
