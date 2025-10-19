
import os, asyncio, html
from typing import List
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from boostx_ext.balance import get_balance, create_invoice, confirm_invoice
from boostx_ext.looksmm import services as looksmm_services, add_order as looksmm_add

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PAY_INSTRUCTIONS = os.getenv("PAY_INSTRUCTIONS", "Переведите точную сумму на карту и отправьте номер транзакции в ответ.")

def register_balance_handlers(app: Application):
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("topup", cmd_topup))
    app.add_handler(CommandHandler("confirm_payment", cmd_confirm_payment))
    app.add_handler(CommandHandler("services", cmd_services))
    app.add_handler(CommandHandler("buy", cmd_buy))

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bal = get_balance(uid)
    await update.message.reply_html(f"💳 <b>Ваш баланс:</b> <code>{bal:.2f} ₽</code>")

async def cmd_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /topup 500
    if not context.args:
        await update.message.reply_text("Использование: /topup <сумма>
Например: /topup 300")
        return
    try:
        amount = float(context.args[0])
        if amount <= 0:
            raise ValueError
    except Exception:
        await update.message.reply_text("Укажи сумму числом больше 0. Например: /topup 300")
        return
    inv = create_invoice(update.effective_user.id, amount)
    text = (
        f"🧾 <b>Счёт на пополнение</b>
"
        f"ID: <code>{inv['invoice_id']}</code>
"
        f"Сумма: <b>{amount:.2f} ₽</b>

"
        f"{html.escape(PAY_INSTRUCTIONS)}

"
        f"После оплаты админ подтвердит перевод командой /confirm_payment {inv['invoice_id']}"
    )
    await update.message.reply_html(text)

async def cmd_confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Недостаточно прав.")
        return
    if not context.args:
        await update.message.reply_text("Использование: /confirm_payment <invoice_id>")
        return
    inv_id = context.args[0]
    inv = confirm_invoice(inv_id)
    if not inv:
        await update.message.reply_text("Счёт не найден.")
        return
    await update.message.reply_text(f"✅ Оплата подтверждена. Баланс пользователя {inv['user_id']} пополнен на {inv['amount']:.2f} ₽.")

async def cmd_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = await asyncio.to_thread(looksmm_services)
        # Возьмём первые 10 услуг для краткости
        lines = ["📋 Список услуг (первые 10):"]
        for s in data[:10]:
            rate = s.get("rate") or s.get("price") or "—"
            lines.append(f"• {s['service']}: {s['name']} — {rate} ₽/1000")
        lines.append("\nКупить: /buy <service_id> <ссылка> <кол-во>")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Ошибка получения услуг: {e}")

async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /buy 1 https://instagram.com/instagram 100
    if len(context.args) < 3:
        await update.message.reply_text("Использование: /buy <service_id> <ссылка> <кол-во>")
        return
    uid = update.effective_user.id
    try:
        service_id = int(context.args[0])
        link = context.args[1]
        qty = int(context.args[2])
    except Exception:
        await update.message.reply_text("Проверь параметры. Пример: /buy 1 https://instagram.com/instagram 100")
        return
    from boostx_ext.balance import get_balance, set_balance
    # Получим цену услуги (rate за 1000)
    try:
        data = await asyncio.to_thread(looksmm_services)
        svc = next((x for x in data if int(x.get("service")) == service_id), None)
        if not svc:
            await update.message.reply_text("Услуга не найдена.")
            return
        rate = float(svc.get("rate") or 0.0)  # руб за 1000
        cost = rate * (qty / 1000.0)
    except Exception as e:
        await update.message.reply_text(f"Ошибка получения услуги: {e}")
        return
    bal = get_balance(uid)
    if bal < cost:
        await update.message.reply_text(f"Недостаточно средств. Нужно ~{cost:.2f} ₽, на балансе {bal:.2f} ₽. Пополнить: /topup <сумма>")
        return
    # Списываем и создаём заказ
    set_balance(uid, bal - cost)
    try:
        resp = await asyncio.to_thread(looksmm_add, service_id, link, qty)
        order_id = resp.get("order") or resp
        await update.message.reply_text(f"✅ Заказ создан в системе поставщика.
ID: {order_id}
Списано {cost:.2f} ₽.
Текущий баланс: {get_balance(uid):.2f} ₽")
    except Exception as e:
        # Возвращаем баланс при ошибке
        set_balance(uid, bal)
        await update.message.reply_text(f"Ошибка создания заказа: {e}")
