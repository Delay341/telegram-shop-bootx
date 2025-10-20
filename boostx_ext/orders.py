
import os, json, time
from pathlib import Path

ORDERS_FILE = Path(os.getenv("ORDERS_FILE", "orders.json"))

def _read():
    if not ORDERS_FILE.exists():
        return []
    try:
        return json.loads(ORDERS_FILE.read_text("utf-8"))
    except Exception:
        return []

def _write(data):
    ORDERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def append_order(order: dict):
    order["created_at"] = int(time.time())
    data = _read()
    data.append(order)
    _write(data)
