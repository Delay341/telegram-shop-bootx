import os, requests, time
API_BASE = os.getenv("SUPPLIER_API_URL", "https://looksmm.ru/api/v2")
API_KEY = os.getenv("SUPPLIER_API_KEY", "")

_services_cache = {"ts":0,"data":[]}

def _post(payload: dict):
    data = dict(payload); data["key"]=API_KEY
    r = requests.post(API_BASE, data=data, timeout=30)
    try:
        return r.status_code, r.text, r.json()
    except Exception:
        return r.status_code, r.text, None

def get_services(force=False):
    now = int(time.time())
    if not force and _services_cache["data"] and now - _services_cache["ts"] < 3600:
        return _services_cache["data"]
    c,t,j = _post({"action":"services"})
    if isinstance(j, list):
        _services_cache["ts"]=now; _services_cache["data"]=j; return j
    raise RuntimeError(f"Supplier services not JSON list: {t[:200]}")

def add_order(service_id, link, quantity):
    c,t,j = _post({"action":"add","service":service_id,"link":link,"quantity":quantity})
    if j is None: raise RuntimeError(f"Add order not JSON: {t[:200]}")
    return j
