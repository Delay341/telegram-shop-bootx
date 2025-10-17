import os, requests
API_BASE = os.getenv("SUPPLIER_API_URL", "https://looksmm.ru/api/v2")
API_KEY = os.getenv("SUPPLIER_API_KEY", "")
def _post(payload: dict):
    data = dict(payload); data["key"]=API_KEY
    r = requests.post(API_BASE, data=data, timeout=30)
    try:
        return r.status_code, r.text, r.json()
    except Exception:
        return r.status_code, r.text, None
def get_services():
    c,t,j = _post({"action":"services"})
    if j is None: raise RuntimeError(f"Supplier not JSON: {t[:200]}")
    return j
def add_order(service_id, link, quantity):
    c,t,j = _post({"action":"add","service":service_id,"link":link,"quantity":quantity})
    if j is None: raise RuntimeError(f"Add order not JSON: {t[:200]}")
    return j
