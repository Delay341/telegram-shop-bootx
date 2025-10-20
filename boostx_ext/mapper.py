
import json, re
from pathlib import Path
from typing import Dict

MAP_PATH = Path("config/service_map.json")

def load_map() -> Dict[str, int]:
    if MAP_PATH.exists():
        try:
            return json.loads(MAP_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_map(m: Dict[str, int]) -> None:
    MAP_PATH.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

def norm(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[\[\](){}]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s

def title_key(cat_title: str, item_title: str) -> str:
    return f"{cat_title}:::{item_title}"

def get_mapped_id(cat_title: str, item_title: str) -> int | None:
    return load_map().get(title_key(cat_title, item_title))
