"""
Background crawler — ყოველ 5 წუთში ავტომატურად ახლებს ფასებს.

არქიტექტურა:
  - ცალკე thread-ი მუშაობს Flask-ის გვერდით
  - ეძებს პოპულარულ პროდუქტებს + ბოლო ძიებებს
  - ინახავს SQLite-ში (products ცხრილი)
  - ძიება ამ ცხრილიდან = მყისიერი (< 50ms)
"""

import json
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Common Georgian products to pre-fetch ─────────────────────────────────────
SEED_QUERIES = [
    # სუპერმარკეტი
    "კარაქი", "კვერცხი", "პური", "ყველი", "რძე", "ძეხვი",
    "ქათამი", "ღორის ხორცი", "ბრინჯი", "მაკარონი", "ზეთი",
    "შაქარი", "მარილი", "ყავა", "ჩაი", "წვენი", "კოლა",
    "ხახვი", "კარტოფილი", "პომიდორი", "ვაშლი", "ბანანი",
    "ნიორი", "სოუსი", "მაიონეზი", "კეჩუპი", "გოჭი",
    # ჰიგიენა
    "შამპუნი", "კბილის პასტა", "საპონი", "ჰაგისი", "პამპერსი",
    # აფთიაქი
    "ამოქსიცილინი", "ნო-შპა", "პარაცეტამოლი", "იბუპროფენი",
    "ვიტამინი C", "ფესტალი", "სმექტა", "ციტრამონი",
    # ბრენდები
    "President", "Nikora", "Avedo",
]

CRAWL_INTERVAL = 300   # 5 minutes
PRODUCT_TTL    = 600   # 10 minutes — products older than this are considered stale
WORKERS        = 6     # parallel scraper threads per cycle


class BackgroundCrawler:
    def __init__(self, db_path: str, get_scrapers_fn):
        self.db_path        = db_path
        self.get_scrapers   = get_scrapers_fn   # callable → list of scrapers
        self._stop          = threading.Event()
        self._thread        = None
        self._crawl_lock    = threading.Lock()
        self.last_crawl_at  = 0.0
        self.crawl_count    = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Start background thread. Called once at server startup."""
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="crawler"
        )
        self._thread.start()
        print("[crawler] Started - first crawl in 10 seconds")

    def stop(self):
        self._stop.set()

    def status(self) -> dict:
        next_in = max(0, int(CRAWL_INTERVAL - (time.time() - self.last_crawl_at)))
        return {
            "last_crawl_at": self.last_crawl_at or None,
            "crawl_count": self.crawl_count,
            "next_crawl_in_seconds": next_in,
            "product_count": self._count_products(),
        }

    def search_local(self, query: str) -> list[dict]:
        """
        Full-text search in local products table.
        Returns results sorted by price. Empty list if nothing fresh found.
        """
        normalized = query.strip().lower()
        words = [w for w in normalized.split() if len(w) > 1]
        if not words:
            return []

        since = time.time() - PRODUCT_TTL
        # Match any word in product_name (case-insensitive)
        conditions = " OR ".join(["LOWER(product_name) LIKE ?" for _ in words])
        params = [f"%{w}%" for w in words] + [since]

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""SELECT * FROM products
                    WHERE ({conditions}) AND scraped_at > ?
                    ORDER BY current_price ASC
                    LIMIT 50""",
                params
            ).fetchall()

        return [dict(r) for r in rows]

    def trigger_query(self, query: str):
        """
        When a user searches for something not in the local DB,
        schedule an immediate background crawl for that query.
        """
        threading.Thread(
            target=self._crawl_query,
            args=(query,),
            daemon=True,
            name=f"crawl-{query[:20]}"
        ).start()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _loop(self):
        # First crawl after a short delay so the server finishes starting
        time.sleep(10)
        while not self._stop.is_set():
            self._full_cycle()
            self._stop.wait(CRAWL_INTERVAL)

    def _full_cycle(self):
        """One complete crawl cycle: seed queries + recent user searches."""
        if not self._crawl_lock.acquire(blocking=False):
            return   # already running
        try:
            t0 = time.time()
            scrapers = self.get_scrapers()
            if not scrapers:
                return

            # Combine seed list with recent user searches
            recent = self._recent_queries(limit=20)
            queries = list(dict.fromkeys(SEED_QUERIES + recent))  # deduplicate, preserve order

            print(f"[crawler] Cycle #{self.crawl_count+1}: {len(queries)} queries × {len(scrapers)} stores")

            total_saved = 0
            for query in queries:
                if self._stop.is_set():
                    break
                saved = self._crawl_query(query, scrapers)
                total_saved += saved

            elapsed = time.time() - t0
            self.last_crawl_at = time.time()
            self.crawl_count  += 1
            print(f"[crawler] Cycle done in {elapsed:.0f}s — {total_saved} products saved")

        finally:
            self._crawl_lock.release()

    def _crawl_query(self, query: str, scrapers=None) -> int:
        """Scrape all stores for one query and save to DB. Returns saved count."""
        if scrapers is None:
            scrapers = self.get_scrapers()

        all_results = []
        pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="crawler")
        futures = {
            pool.submit(self._scrape_one, scraper, query): scraper.store_name
            for scraper in scrapers
        }
        try:
            for future in as_completed(futures, timeout=9):
                try:
                    results = future.result(timeout=0)
                    all_results.extend(results)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            pool.shutdown(wait=False)

        if all_results:
            self._upsert_products(query, all_results)
        return len(all_results)

    @staticmethod
    def _scrape_one(scraper, query: str) -> list[dict]:
        try:
            return [r.to_dict() for r in scraper.search(query)]
        except Exception:
            return []

    def _upsert_products(self, query: str, results: list[dict]):
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            for r in results:
                try:
                    conn.execute(
                        """INSERT OR REPLACE INTO products
                           (store_name, product_name, current_price, original_price,
                            discount_percent, product_url, image_url, in_stock,
                            search_keyword, scraped_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (
                            r.get("store_name"), r.get("product_name"),
                            r.get("current_price"), r.get("original_price"),
                            r.get("discount_percent"), r.get("product_url"),
                            r.get("image_url"), 1 if r.get("in_stock", True) else 0,
                            query.strip().lower(), now,
                        )
                    )
                except Exception:
                    pass
            conn.commit()

    def _recent_queries(self, limit: int = 20) -> list[str]:
        since = time.time() - 86400  # last 24 hours
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """SELECT DISTINCT query FROM search_history
                       WHERE searched_at > ? ORDER BY searched_at DESC LIMIT ?""",
                    (since, limit)
                ).fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    def _count_products(self) -> int:
        try:
            since = time.time() - PRODUCT_TTL
            with sqlite3.connect(self.db_path) as conn:
                return conn.execute(
                    "SELECT COUNT(*) FROM products WHERE scraped_at > ?", (since,)
                ).fetchone()[0]
        except Exception:
            return 0


# Module-level singleton (created in main.py)
_crawler: BackgroundCrawler | None = None


def get_crawler() -> BackgroundCrawler | None:
    return _crawler


def init_crawler(db_path: str, get_scrapers_fn) -> BackgroundCrawler:
    global _crawler
    _crawler = BackgroundCrawler(db_path, get_scrapers_fn)
    _crawler.start()
    return _crawler
