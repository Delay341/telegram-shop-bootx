# handlers/admin_exports.py
import os, json, csv, io
from pathlib import Path
from telebot import TeleBot

ORDERS_FILE = Path(os.getenv("ORDERS_FILE", Path(__file__).resolve().parent.parent / "orders.json"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)

def _load_orders():
    if ORDERS_FILE.exists():
        try:
            return json.loads(ORDERS_FILE.read_text("utf-8"))
        except Exception:
            return []
    return []

def _to_csv_bytes(rows):
    # rows is list[dict]
    if not rows:
        rows = []
    # Collect headers
    headers = set()
    for r in rows:
        headers.update(r.keys())
    headers = sorted(headers)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers)
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k, "") for k in headers})
    return buf.getvalue().encode("utf-8")

def register_admin_exports(bot: TeleBot):
    @bot.message_handler(commands=['orders_json'])
    def orders_json(m):
        if m.from_user.id != ADMIN_ID:
            return
        data = _load_orders()
        content = json.dumps(data, ensure_ascii=False, indent=2)
        bot.send_document(m.chat.id, ("orders.json", io.BytesIO(content.encode("utf-8"))))

    @bot.message_handler(commands=['orders_csv'])
    def orders_csv(m):
        if m.from_user.id != ADMIN_ID:
            return
        data = _load_orders()
        csv_bytes = _to_csv_bytes(data if isinstance(data, list) else [])
        bot.send_document(m.chat.id, ("orders.csv", io.BytesIO(csv_bytes)))
