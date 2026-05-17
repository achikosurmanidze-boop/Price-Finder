"""
Flask backend — ქართული ფასების შედარების API
გაშვება: py main.py
"""

import json
import os
import sqlite3
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import time
from threading import Lock

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

from agent import run_agent
from basket_agent import run_basket_agent
from crawler import init_crawler, get_crawler
from scrapers import ALL_SCRAPERS

app = Flask(__name__, static_folder=None)
CORS(app)

DB_PATH       = os.path.join(BASE_DIR, "price_cache.db")
CACHE_DURATION = int(os.getenv("CACHE_DURATION_SECONDS", "7200"))
_db_lock      = Lock()


# ── Database init ─────────────────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS search_cache (
                query      TEXT PRIMARY KEY,
                results    TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS search_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                query       TEXT NOT NULL,
                searched_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_searched_at ON search_history(searched_at);

            -- Background crawler product store
            CREATE TABLE IF NOT EXISTS products (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                store_name       TEXT NOT NULL,
                product_name     TEXT NOT NULL,
                current_price    REAL NOT NULL,
                original_price   REAL,
                discount_percent REAL,
                product_url      TEXT,
                image_url        TEXT,
                in_stock         INTEGER DEFAULT 1,
                search_keyword   TEXT,
                scraped_at       REAL NOT NULL,
                UNIQUE(store_name, product_url)
            );
            CREATE INDEX IF NOT EXISTS idx_products_keyword  ON products(search_keyword);
            CREATE INDEX IF NOT EXISTS idx_products_scraped  ON products(scraped_at);
            CREATE INDEX IF NOT EXISTS idx_products_name     ON products(product_name);

            -- Shopping lists
            CREATE TABLE IF NOT EXISTS shopping_lists (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS list_items (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                list_id      INTEGER NOT NULL REFERENCES shopping_lists(id) ON DELETE CASCADE,
                product_name TEXT NOT NULL,
                checked      INTEGER DEFAULT 0,
                frequent     INTEGER DEFAULT 0,
                added_at     REAL NOT NULL
            );

            -- Price alerts
            CREATE TABLE IF NOT EXISTS price_alerts (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name     TEXT NOT NULL,
                target_price     REAL,
                active           INTEGER DEFAULT 1,
                last_notified_at REAL,
                created_at       REAL NOT NULL
            );
        """)
        conn.commit()


# ── Cache helpers ─────────────────────────────────────────────────────────────

def get_cached(query: str):
    normalized = query.strip().lower()
    with _db_lock:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT results, created_at FROM search_cache WHERE query = ?",
                (normalized,)
            ).fetchone()
            if row:
                if time.time() - row["created_at"] < CACHE_DURATION:
                    return json.loads(row["results"])
                conn.execute("DELETE FROM search_cache WHERE query = ?", (normalized,))
                conn.commit()
    return None


def set_cache(query: str, payload: dict):
    normalized = query.strip().lower()
    with _db_lock:
        with get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO search_cache (query, results, created_at) VALUES (?,?,?)",
                (normalized, json.dumps(payload, ensure_ascii=False), time.time())
            )
            conn.commit()


def record_search(query: str):
    with _db_lock:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO search_history (query, searched_at) VALUES (?,?)",
                (query.strip(), time.time())
            )
            conn.commit()


# ── Alert check ───────────────────────────────────────────────────────────────

def check_alerts_for_results(results: list) -> list:
    triggered = []
    with get_conn() as conn:
        alerts = conn.execute(
            "SELECT * FROM price_alerts WHERE active = 1"
        ).fetchall()

    for alert in alerts:
        alert_name = alert["product_name"].lower()
        for r in results:
            if (alert_name in r.get("product_name", "").lower()
                    and r.get("discount_percent") and r["discount_percent"] > 0
                    and ((alert["target_price"] is None)
                         or (r.get("current_price", 9999) <= alert["target_price"]))):
                triggered.append({
                    "alert_id":        alert["id"],
                    "product_name":    alert["product_name"],
                    "store":           r["store_name"],
                    "current_price":   r["current_price"],
                    "discount_percent":r["discount_percent"],
                    "product_url":     r.get("product_url"),
                })
                with _db_lock:
                    with get_conn() as conn2:
                        conn2.execute(
                            "UPDATE price_alerts SET last_notified_at=? WHERE id=?",
                            (time.time(), alert["id"])
                        )
                        conn2.commit()
    return triggered


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Basic Search
# ══════════════════════════════════════════════════════════════════════════════

FRONTEND_PATH = os.path.join(BASE_DIR, "index.html")

@app.get("/")
def index():
    if os.path.exists(FRONTEND_PATH):
        response = send_file(FRONTEND_PATH, max_age=0)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    return jsonify({"status": "ok", "message": "Georgian Price Finder API"}), 200



@app.get("/health")
def health():
    crawler = get_crawler()
    return jsonify({
        "status": "ok",
        "message": "Georgian Price Finder is running!",
        "crawler": crawler.status() if crawler else None,
        "active_scrapers": [s.store_name for s in ALL_SCRAPERS],
    })


@app.post("/api/search")
def search():
    data  = request.get_json(force=True, silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "Query cannot be empty"}), 400
    if len(query) > 200:
        return jsonify({"error": "Query too long"}), 400

    record_search(query)

    # ── 1. Check search_cache (2-hour cache) ──────────────────────────────────
    cached = get_cached(query)
    if cached is not None:
        alerts = check_alerts_for_results(cached.get("results", []))
        return jsonify({"query": query, "source": "cache", "alerts": alerts, **cached})

    # ── 2. Check local products DB (from background crawler) ──────────────────
    crawler = get_crawler()
    if crawler:
        local = crawler.search_local(query)
        if local:
            results = sorted(local, key=lambda x: x.get("current_price") or 999)
            if results:
                results[0]["is_cheapest"] = True
            payload = {
                "results": results,
                "summary": f"ადგილობრივი ბაზიდან — {len(results)} შედეგი '{query}'. ფასები განახლებულია.",
            }
            set_cache(query, payload)
            alerts = check_alerts_for_results(results)
            return jsonify({"query": query, "source": "local_db", "alerts": alerts, **payload})

    # ── 3. Live scrape + Claude (fallback, ~10-15s) ───────────────────────────
    # Trigger a background crawl so next time it's instant
    if crawler:
        crawler.trigger_query(query)

    try:
        agent_result = run_agent(query)
    except Exception as exc:
        return jsonify({"error": f"Agent error: {exc}"}), 500

    results = agent_result.get("results", [])
    summary = agent_result.get("summary", "")
    results.sort(key=lambda x: x.get("current_price") or float("inf"))
    if results:
        results[0]["is_cheapest"] = True

    payload = {"results": results, "summary": summary}
    set_cache(query, payload)
    alerts = check_alerts_for_results(results)
    return jsonify({"query": query, "source": "live", "alerts": alerts, **payload})


@app.get("/api/trending")
def trending():
    since = time.time() - 86400
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT query, COUNT(*) as cnt FROM search_history
               WHERE searched_at > ? GROUP BY LOWER(query)
               ORDER BY cnt DESC LIMIT 10""",
            (since,)
        ).fetchall()
    return jsonify({"trending": [{"query": r["query"], "count": r["cnt"]} for r in rows]})


@app.get("/api/crawler/status")
def crawler_status():
    c = get_crawler()
    if not c:
        return jsonify({"error": "Crawler not running"}), 503
    return jsonify(c.status())


@app.post("/api/crawler/crawl-now")
def crawl_now():
    """Manually trigger a full crawl cycle (for admin use)."""
    c = get_crawler()
    if not c:
        return jsonify({"error": "Crawler not running"}), 503
    import threading
    threading.Thread(target=c._full_cycle, daemon=True).start()
    return jsonify({"ok": True, "message": "Crawl started in background"})


@app.post("/api/dev/clear-cache")
def clear_cache():
    with _db_lock:
        with get_conn() as conn:
            conn.execute("DELETE FROM search_cache")
            conn.commit()
    return jsonify({"ok": True})


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Basket
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/basket")
def basket():
    data  = request.get_json(force=True, silent=True) or {}
    items = data.get("items", [])
    if not items or not isinstance(items, list):
        return jsonify({"error": "items must be a non-empty list"}), 400
    items = [str(i).strip() for i in items if str(i).strip()]
    if not items:
        return jsonify({"error": "items list is empty"}), 400
    if len(items) > 20:
        return jsonify({"error": "Maximum 20 items per basket"}), 400

    cache_key = "basket:" + "|".join(sorted(i.lower() for i in items))
    cached = get_cached(cache_key)
    if cached:
        return jsonify({"from_cache": True, **cached})

    # Check local DB for each item
    crawler = get_crawler()
    if crawler:
        item_data = {}
        missing   = []
        for item in items:
            local = crawler.search_local(item)
            if local:
                item_data[item] = local
            else:
                missing.append(item)

        # If all items found locally, do lightweight basket math without Claude
        if not missing and item_data:
            result = _local_basket_analysis(items, item_data)
            set_cache(cache_key, result)
            return jsonify({"from_cache": False, "source": "local_db", **result})

        # Trigger background crawl for missing items
        for item in missing:
            crawler.trigger_query(item)

    try:
        result = run_basket_agent(items)
    except Exception as exc:
        return jsonify({"error": f"Basket agent error: {exc}"}), 500

    set_cache(cache_key, result)
    return jsonify({"from_cache": False, "source": "live", **result})


def _local_basket_analysis(items: list, item_data: dict) -> dict:
    """Fast basket math from local DB — no Claude needed."""
    per_item = []
    store_totals: dict[str, dict] = {}

    for item in items:
        results = sorted(item_data[item], key=lambda x: x.get("current_price") or 999)
        if not results:
            continue

        # Cheapest overall
        cheapest = results[0]
        all_stores = []
        seen = {}
        for r in results:
            s = r["store_name"]
            if s not in seen:
                seen[s] = r
                all_stores.append({
                    "store":        s,
                    "price":        r["current_price"],
                    "product_name": r["product_name"],
                    "url":          r.get("product_url"),
                    "discount_percent": r.get("discount_percent"),
                })

        per_item.append({
            "item":           item,
            "cheapest_store": cheapest["store_name"],
            "cheapest_price": cheapest["current_price"],
            "cheapest_url":   cheapest.get("product_url"),
            "all_stores":     all_stores,
        })

        # Accumulate per-store totals (cheapest available per store)
        for s, r in seen.items():
            if s not in store_totals:
                store_totals[s] = {"total": 0.0, "items_found": 0}
            store_totals[s]["total"]       += r["current_price"]
            store_totals[s]["items_found"] += 1

    if not store_totals:
        return {"per_item": per_item, "basket_comparison": [], "best_single_store": None,
                "best_single_total": None, "split_strategy": [], "split_total": None,
                "summary": "პროდუქტები ვერ მოიძებნა"}

    n_items   = len(items)
    max_total = max(v["total"] for v in store_totals.values())

    basket_comparison = sorted([
        {
            "store":         store,
            "total":         round(vals["total"], 2),
            "items_found":   vals["items_found"],
            "items_total":   n_items,
            "savings_vs_max": round(max_total - vals["total"], 2),
        }
        for store, vals in store_totals.items()
    ], key=lambda x: x["total"])

    best  = basket_comparison[0]
    split: dict[str, dict] = {}  # store → {items:[], subtotal:0}
    for pi in per_item:
        s = pi["cheapest_store"]
        if s not in split:
            split[s] = {"store": s, "items": [], "subtotal": 0.0}
        split[s]["items"].append(pi["item"])
        split[s]["subtotal"] += pi["cheapest_price"]

    split_list  = [{"store": v["store"], "items": v["items"], "subtotal": round(v["subtotal"], 2)}
                   for v in split.values()]
    split_total = round(sum(v["subtotal"] for v in split_list), 2)

    summary = (
        f"ყველაზე იაფი ერთ მაღაზიაში: {best['store']} — {best['total']:.2f}₾. "
    )
    if split_total < best["total"] - 0.1:
        saving = round(best["total"] - split_total, 2)
        summary += f"სხვადასხვა მაღაზიებში ყიდვით კიდე {saving:.2f}₾ დაზოგავ."

    return {
        "per_item":          per_item,
        "basket_comparison": basket_comparison,
        "best_single_store": best["store"],
        "best_single_total": best["total"],
        "split_strategy":    split_list if split_total < best["total"] - 0.1 else [],
        "split_total":       split_total if split_total < best["total"] - 0.1 else None,
        "summary":           summary,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Shopping Lists & Alerts  (unchanged from before)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/lists")
def get_lists():
    with get_conn() as conn:
        lists = conn.execute("SELECT * FROM shopping_lists ORDER BY updated_at DESC").fetchall()
        result = []
        for lst in lists:
            items = conn.execute(
                "SELECT * FROM list_items WHERE list_id=? ORDER BY added_at", (lst["id"],)
            ).fetchall()
            result.append({**dict(lst), "items": [dict(i) for i in items]})
    return jsonify({"lists": result})


@app.post("/api/lists")
def create_list():
    data  = request.get_json(force=True, silent=True) or {}
    name  = (data.get("name") or "ჩემი სია").strip()
    items = data.get("items", [])
    now   = time.time()
    with _db_lock:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO shopping_lists (name,created_at,updated_at) VALUES (?,?,?)",
                (name, now, now)
            )
            lid = cur.lastrowid
            for item in items:
                n = str(item).strip()
                if n:
                    conn.execute(
                        "INSERT INTO list_items (list_id,product_name,added_at) VALUES (?,?,?)",
                        (lid, n, now)
                    )
            conn.commit()
    return jsonify({"id": lid, "name": name, "items": items}), 201


@app.get("/api/lists/<int:list_id>")
def get_list(list_id):
    with get_conn() as conn:
        lst = conn.execute("SELECT * FROM shopping_lists WHERE id=?", (list_id,)).fetchone()
        if not lst:
            return jsonify({"error": "List not found"}), 404
        items = conn.execute(
            "SELECT * FROM list_items WHERE list_id=? ORDER BY added_at", (list_id,)
        ).fetchall()
    return jsonify({**dict(lst), "items": [dict(i) for i in items]})


@app.delete("/api/lists/<int:list_id>")
def delete_list(list_id):
    with _db_lock:
        with get_conn() as conn:
            conn.execute("DELETE FROM shopping_lists WHERE id=?", (list_id,))
            conn.commit()
    return jsonify({"ok": True})


@app.post("/api/lists/<int:list_id>/items")
def add_item(list_id):
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("product_name") or "").strip()
    if not name:
        return jsonify({"error": "product_name is required"}), 400
    now = time.time()
    with _db_lock:
        with get_conn() as conn:
            if not conn.execute("SELECT id FROM shopping_lists WHERE id=?", (list_id,)).fetchone():
                return jsonify({"error": "List not found"}), 404
            cur = conn.execute(
                "INSERT INTO list_items (list_id,product_name,added_at) VALUES (?,?,?)",
                (list_id, name, now)
            )
            conn.execute("UPDATE shopping_lists SET updated_at=? WHERE id=?", (now, list_id))
            conn.commit()
    return jsonify({"id": cur.lastrowid, "product_name": name}), 201


@app.patch("/api/lists/<int:list_id>/items/<int:item_id>")
def update_item(list_id, item_id):
    data    = request.get_json(force=True, silent=True) or {}
    updates = {}
    if "checked"      in data: updates["checked"]      = 1 if data["checked"] else 0
    if "frequent"     in data: updates["frequent"]     = 1 if data["frequent"] else 0
    if "product_name" in data:
        n = str(data["product_name"]).strip()
        if n: updates["product_name"] = n
    if not updates:
        return jsonify({"error": "Nothing to update"}), 400
    clause = ", ".join(f"{k}=?" for k in updates)
    vals   = list(updates.values()) + [item_id, list_id]
    with _db_lock:
        with get_conn() as conn:
            conn.execute(f"UPDATE list_items SET {clause} WHERE id=? AND list_id=?", vals)
            conn.execute("UPDATE shopping_lists SET updated_at=? WHERE id=?", (time.time(), list_id))
            conn.commit()
    return jsonify({"ok": True})


@app.delete("/api/lists/<int:list_id>/items/<int:item_id>")
def delete_item(list_id, item_id):
    with _db_lock:
        with get_conn() as conn:
            conn.execute("DELETE FROM list_items WHERE id=? AND list_id=?", (item_id, list_id))
            conn.execute("UPDATE shopping_lists SET updated_at=? WHERE id=?", (time.time(), list_id))
            conn.commit()
    return jsonify({"ok": True})


@app.get("/api/alerts")
def get_alerts():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM price_alerts ORDER BY created_at DESC").fetchall()
    return jsonify({"alerts": [dict(r) for r in rows]})


@app.post("/api/alerts")
def create_alert():
    data         = request.get_json(force=True, silent=True) or {}
    product_name = (data.get("product_name") or "").strip()
    if not product_name:
        return jsonify({"error": "product_name is required"}), 400
    target = data.get("target_price")
    if target is not None:
        try:    target = float(target)
        except: return jsonify({"error": "target_price must be a number"}), 400
    with _db_lock:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO price_alerts (product_name,target_price,created_at) VALUES (?,?,?)",
                (product_name, target, time.time())
            )
            conn.commit()
    return jsonify({"id": cur.lastrowid, "product_name": product_name, "target_price": target}), 201


@app.delete("/api/alerts/<int:alert_id>")
def delete_alert(alert_id):
    with _db_lock:
        with get_conn() as conn:
            conn.execute("DELETE FROM price_alerts WHERE id=?", (alert_id,))
            conn.commit()
    return jsonify({"ok": True})


@app.patch("/api/alerts/<int:alert_id>")
def toggle_alert(alert_id):
    data   = request.get_json(force=True, silent=True) or {}
    active = 1 if data.get("active", True) else 0
    with _db_lock:
        with get_conn() as conn:
            conn.execute("UPDATE price_alerts SET active=? WHERE id=?", (active, alert_id))
            conn.commit()
    return jsonify({"ok": True})


@app.get("/api/alerts/check")
def check_alerts():
    triggered = []
    with get_conn() as conn:
        alerts     = conn.execute("SELECT * FROM price_alerts WHERE active=1").fetchall()
        cache_rows = conn.execute("SELECT results FROM search_cache").fetchall()
    for alert in alerts:
        name = alert["product_name"].lower()
        for row in cache_rows:
            try:
                for r in json.loads(row["results"]).get("results", []):
                    if (name in r.get("product_name","").lower()
                            and r.get("discount_percent", 0) > 0
                            and (alert["target_price"] is None
                                 or r.get("current_price", 9999) <= alert["target_price"])):
                        triggered.append({
                            "alert_id":         alert["id"],
                            "product_name":     alert["product_name"],
                            "store":            r["store_name"],
                            "current_price":    r["current_price"],
                            "discount_percent": r["discount_percent"],
                            "product_url":      r.get("product_url"),
                        })
            except Exception:
                continue
    return jsonify({"triggered": triggered})


# ══════════════════════════════════════════════════════════════════════════════
# Start
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_db()
    crawler_enabled = os.getenv("ENABLE_CRAWLER", "1") != "0"
    if crawler_enabled:
        init_crawler(DB_PATH, lambda: ALL_SCRAPERS)

    port = int(os.getenv("PORT", "8001"))

    print("\n" + "=" * 52)
    print("  Georgian Price Finder - fasebis shemdarebleli")
    print("=" * 52)
    print(f"  API:      http://localhost:{port}")
    print(f"  Frontend: http://localhost:{port}/")
    print(f"  Scrapers: {', '.join(s.store_name for s in ALL_SCRAPERS)}")
    print(f"  Crawler:  {'every 5 min' if crawler_enabled else 'disabled'}, {len(ALL_SCRAPERS)} stores")
    print("=" * 52 + "\n")

    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
