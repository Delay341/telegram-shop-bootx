import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from boostx_ext.balance import get_balance, set_balance, create_invoice, confirm_invoice

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PAY_INSTRUCTIONS = os.getenv("PAY_INSTRUCTIONS","Переведите точную сумму на карту и отправьте номер транзакции в ответ.")
PAY_URL = os.getenv("PAY_URL","https://www.tinkoff.ru/rm/r_nIutIhQtbX.tRouMxMcdC/kgUL962390")

def register_balance_handlers(app: Application):
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("topup", cmd_topup))
    app.add_handler(CommandHandler("confirm_payment", cmd_confirm_payment))
    app.add_handler(CommandHandler("buy", cmd_buy_stub))

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bal = get_balance(uid)
    await update.message.reply_html(f"💳 <b>Ваш баланс:</b> <code>{bal:.2f} ₽</code>")

async def cmd_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /topup &lt;сумма&gt;")
        return
    try:
        amount = float(context.args[0])
        if amount <= 0:
            raise ValueError
    except Exception:
        await update.message.reply_text("Укажи сумму числом больше 0. Например: /topup 300")
        return

    inv = create_invoice(update.effective_user.id, amount)
    uname = update.effective_user.username or "username"

    text = (
        f"🧾 <b>Счёт на пополнение</b>\n"
        f"ID: <code>{inv['invoice_id']}</code>\n"
        f"Сумма: <b>{amount:.2f} ₽</b>\n\n"
        f"👉 <a href=\"{PAY_URL}\">Ссылка на оплату</a>\n\n"
        f"В сообщении к переводу укажите: Ваш @{uname} и номер счёта (ID): "
        f"<code>{inv['invoice_id']}</code>\n\n"
        f"После оплаты админ подтвердит перевод командой /confirm_payment {inv['invoice_id']}"
    )
    await update.message.reply_html(text)

async def cmd_confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Недостаточно прав.")
        return
    if not context.args:
        await update.message.reply_text("Использование: /confirm_payment &lt;invoice_id&gt;")
        return

    inv_id = context.args[0]
    inv = confirm_invoice(inv_id)
    if not inv:
        await update.message.reply_text("Счёт не найден.")
        return

    await update.message.reply_text(
        f"✅ Оплата подтверждена. Баланс пользователя {inv['user_id']} пополнен на {inv['amount']:.2f} ₽."
    )

async def cmd_buy_stub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Покупка оформляется через каталог: /catalog")
