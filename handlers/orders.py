import os, time, json
from telebot import TeleBot
from utils.db import fetch_one, execute, execute_with_lastrowid
from services.supplier import add_order
from utils.notify import log_admin

PRICING_MULTIPLIER = float(os.getenv("PRICING_MULTIPLIER","2.0"))
_stage = {}

def _find_item(config, cat_id, item_id):
    for c in config.get("categories", []):
        if c.get("id")==cat_id:
            for it in c.get("items", []):
                if it.get("id")==item_id:
                    return c, it
    return None, None

def _price(c, it, qty):
    unit = c.get("unit","per_1000")
    base = float(it.get("price",0.0))
    if unit=="per_1000":
        return round(base * (qty/1000.0) * PRICING_MULTIPLIER, 2)
    return round(base * qty * PRICING_MULTIPLIER, 2)

def register_orders(bot: TeleBot, config: dict):
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("item:"))
    def pick_item(cq):
        _, cat_id, item_id = cq.data.split(":",2)
        _stage[cq.from_user.id] = {"cat":cat_id,"item":item_id,"step":"qty"}
        bot.answer_callback_query(cq.id)
        bot.send_message(cq.from_user.id, "Введите количество (число) | Минимальный заказ 10 шт.")

    @bot.message_handler(func=lambda m: _stage.get(m.from_user.id,{}).get("step")=="qty")
    def ask_link(m):
        try: qty = int(m.text.strip())
        except: bot.reply_to(m,"Введите целое число, например 1000"); return
        if qty < 10: bot.reply_to(m, "Минимальный заказ — 10."); return
        st = _stage.get(m.from_user.id,{}); st["qty"]=qty; st["step"]="link"; _stage[m.from_user.id]=st
        bot.reply_to(m, "Отправьте ссылку на пост/видео/запись (куда накрутить).")

    @bot.message_handler(func=lambda m: _stage.get(m.from_user.id,{}).get("step")=="link")
    def place(m):
        link = (m.text or "").strip()
        st = _stage.get(m.from_user.id,{}); cat_id, item_id, qty = st["cat"], st["item"], st["qty"]
        cat, it = _find_item(config, cat_id, item_id)
        if not it: bot.reply_to(m, "Товар не найден."); _stage.pop(m.from_user.id, None); return
        price = _price(cat, it, qty)
        row = fetch_one("SELECT balance FROM users WHERE user_id=?", (m.from_user.id,))
        bal = float(row["balance"]) if row else 0.0
        if bal < price:
            need = round(price - bal, 2)
            bot.reply_to(m, f"Недостаточно средств. Требуется {price:.2f} ₽, на балансе {bal:.2f} ₽. Пополните ещё /topup {need:.2f}")
            _stage.pop(m.from_user.id, None); return
        execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (price, m.from_user.id))
        oid = execute_with_lastrowid("INSERT INTO orders(user_id,service_id,qty,link,price,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                                     (m.from_user.id, it.get("id"), qty, link, price, "pending", int(time.time()), int(time.time())))
        try:
            service_id = it.get("provider_service") or it.get("id")
            resp = add_order(service_id, link, qty)
            provider_oid = str(resp.get("order",""))
            execute("UPDATE orders SET status=?, provider_order_id=?, raw_response=?, updated_at=? WHERE id=?",
                    ("sent", provider_oid, json.dumps(resp, ensure_ascii=False), int(time.time()), oid))
            bot.reply_to(m, f"✅ Заказ #{oid} создан. Списано {price:.2f} ₽. Поставщик: {provider_oid or '—'}")
            log_admin(bot, f"🛒 Заказ #{oid}: item={it.get('id')}, qty={qty}, price={price:.2f}, provider={provider_oid}")
        except Exception as e:
            execute("UPDATE orders SET status=?, raw_response=?, updated_at=? WHERE id=?",
                    ("failed", str(e), int(time.time()), oid))
            execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (price, m.from_user.id))
            bot.reply_to(m, f"❌ Ошибка поставщика: {e}. Средства возвращены на баланс.")
            log_admin(bot, f"❌ Ошибка заказа #{oid}: {e}")
        finally:
            _stage.pop(m.from_user.id, None)
