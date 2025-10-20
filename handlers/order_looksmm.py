import asyncio
from boostx_ext.looksmm import add_order
def compute_cost(price: float, unit: str, mult: float, qty: int) -> float:
    unit_base = 1000.0 if unit == "per_1000" else 100.0
    return float(price) * float(mult) * (qty / unit_base)
async def create_looksmm_order(service_id: int, link: str, qty: int) -> str:
    resp = await asyncio.to_thread(add_order, service_id, link, qty)
    if isinstance(resp, dict) and "order" in resp: return str(resp["order"])
    return str(resp)
