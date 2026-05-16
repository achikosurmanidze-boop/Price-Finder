"""
Loads only scrapers for sites confirmed working by diagnostic.py.
If site_status.json doesn't exist yet, loads all scrapers (safe fallback).
"""
import json
import os

from .carrefour import CarrefourScraper
from .spar      import SparScraper
from .nikora    import NikoraScraper
from .smart     import SmartScraper
from .goodwill  import GoodwillScraper
from .gpc       import GpcScraper
from .aversi    import AversiScraper
from .psp       import PspScraper
from .ili       import IliScraper

# Carrefour and Nikora block scraping (DNS/connection errors) — excluded
_ALL = [
    SparScraper(),
    SmartScraper(),
    GoodwillScraper(),
    GpcScraper(),
    AversiScraper(),
    PspScraper(),
    IliScraper(),
]

_NAME_MAP = {s.store_name: s for s in _ALL}

def _load_active() -> list:
    status_path = os.path.join(os.path.dirname(__file__), "..", "site_status.json")
    status_path = os.path.normpath(status_path)
    if not os.path.exists(status_path):
        # Diagnostic not run yet — use all scrapers
        return list(_ALL)
    try:
        with open(status_path, encoding="utf-8") as f:
            data = json.load(f)
        working_names = data.get("working", [])
        if not working_names:
            return list(_ALL)
        active = [_NAME_MAP[n] for n in working_names if n in _NAME_MAP]
        print(f"[scrapers] Active ({len(active)}): {', '.join(n for n in working_names if n in _NAME_MAP)}")
        return active
    except Exception as e:
        print(f"[scrapers] Could not read site_status.json: {e} — using all")
        return list(_ALL)


ALL_SCRAPERS = _load_active()
