"""
SQLite cache - ინახავს ძიების შედეგებს 2 საათის განმავლობაში.
ამით ვუმცირებთ მაღაზიების სერვერებზე დატვირთვას.
"""
import aiosqlite
import json
import time
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "price_cache.db")
CACHE_DURATION = int(os.getenv("CACHE_DURATION_SECONDS", "7200"))  # 2 hours


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS search_cache (
                query TEXT PRIMARY KEY,
                results TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                searched_at REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_searched_at
            ON search_history(searched_at)
        """)
        await db.commit()


async def get_cached(query: str):
    normalized = query.strip().lower()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT results, created_at FROM search_cache WHERE query = ?",
            (normalized,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                results_json, created_at = row
                age = time.time() - created_at
                if age < CACHE_DURATION:
                    return json.loads(results_json)
                # Expired — delete it
                await db.execute(
                    "DELETE FROM search_cache WHERE query = ?", (normalized,)
                )
                await db.commit()
    return None


async def set_cache(query: str, results: list):
    normalized = query.strip().lower()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO search_cache (query, results, created_at)
               VALUES (?, ?, ?)""",
            (normalized, json.dumps(results, ensure_ascii=False), time.time())
        )
        await db.commit()


async def record_search(query: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO search_history (query, searched_at) VALUES (?, ?)",
            (query.strip(), time.time())
        )
        await db.commit()


async def get_trending(limit: int = 10) -> list[dict]:
    """Returns top searched queries in the last 24 hours."""
    since = time.time() - 86400  # 24 hours
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT query, COUNT(*) as cnt
               FROM search_history
               WHERE searched_at > ?
               GROUP BY LOWER(query)
               ORDER BY cnt DESC
               LIMIT ?""",
            (since, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"query": r[0], "count": r[1]} for r in rows]


async def get_price_history(query: str) -> list[dict]:
    """Returns cached results with timestamps for price history chart."""
    normalized = query.strip().lower()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT results, created_at FROM search_cache WHERE query = ?",
            (normalized,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "results": json.loads(row[0]),
                    "cached_at": row[1]
                }
    return None
