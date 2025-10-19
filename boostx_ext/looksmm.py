
import os, requests
from typing import Any

BASE = "https://looksmm.ru/api/v2"
KEY = os.getenv("LOOKSMM_KEY", "").strip()

def _get(url: str) -> Any:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()

def services() -> Any:
    if not KEY:
        raise RuntimeError("LOOKSMM_KEY is not set")
    url = f"{BASE}?action=services&key={KEY}"
    return _get(url)

def add_order(service: int, link: str, quantity: int) -> Any:
    if not KEY:
        raise RuntimeError("LOOKSMM_KEY is not set")
    url = f"{BASE}?action=add&service={service}&link={link}&quantity={quantity}&key={KEY}"
    return _get(url)
