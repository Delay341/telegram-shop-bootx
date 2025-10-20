import os, json, time, uuid
from pathlib import Path

BALANCES_FILE = Path(os.getenv("BALANCES_FILE", "balances.json"))
INVOICES_FILE = Path(os.getenv("INVOICES_FILE", "invoices.json"))

def _read_json(p: Path):
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return []

def _write_json(p: Path, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def get_balance(user_id: int) -> float:
    for row in _read_json(BALANCES_FILE):
        if row.get("user_id") == user_id:
            return float(row.get("balance", 0))
    return 0.0

def set_balance(user_id: int, value: float) -> float:
    data = _read_json(BALANCES_FILE)
    for row in data:
        if row.get("user_id") == user_id:
            row["balance"] = float(value)
            _write_json(BALANCES_FILE, data)
            return float(value)
    data.append({"user_id": user_id, "balance": float(value)})
    _write_json(BALANCES_FILE, data)
    return float(value)

def add_balance(user_id: int, delta: float) -> float:
    return set_balance(user_id, get_balance(user_id) + float(delta))

def create_invoice(user_id: int, amount: float, note: str | None = None) -> dict:
    inv = {
        "invoice_id": uuid.uuid4().hex,
        "user_id": user_id,
        "amount": float(amount),
        "note": note or "",
        "status": "pending",
        "created_at": int(time.time()),
        "paid_at": None
    }
    data = _read_json(INVOICES_FILE)
    data.append(inv)
    _write_json(INVOICES_FILE, data)
    return inv

def get_invoice(invoice_id: str) -> dict | None:
    for inv in _read_json(INVOICES_FILE):
        if inv.get("invoice_id") == invoice_id:
            return inv
    return None

def confirm_invoice(invoice_id: str) -> dict | None:
    data = _read_json(INVOICES_FILE)
    for inv in data:
        if inv.get("invoice_id") == invoice_id:
            inv["status"] = "paid"
            inv["paid_at"] = int(time.time())
            _write_json(INVOICES_FILE, data)
            add_balance(inv["user_id"], inv["amount"])
            return inv
    return None
