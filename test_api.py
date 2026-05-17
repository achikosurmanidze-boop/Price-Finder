"""Quick API test — runs against localhost:8001 by default. Start the server first."""
import os
import sys
import time
import urllib.request
import urllib.error
import json

BASE = os.getenv("API_BASE", "http://localhost:8001")
OK = 0
FAIL = 0


def req(method, path, body=None, expect=200):
    global OK, FAIL
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    rq = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(rq, timeout=5) as r:
            status = r.status
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            resp = json.loads(e.read())
        except Exception:
            resp = {}
    except Exception as e:
        print(f"  FAIL [{method} {path}]: {e}")
        FAIL += 1
        return None

    if status == expect:
        print(f"  OK   [{method} {path}] -> {status}")
        OK += 1
    else:
        print(f"  FAIL [{method} {path}] -> {status} (expected {expect})")
        FAIL += 1
    return resp


print("=" * 50)
print("  API Test Suite")
print("=" * 50)

# Health
r = req("GET", "/health")
if r:
    print(f"         scrapers: {r.get('active_scrapers', [])}")

# Trending (empty DB is fine)
req("GET", "/api/trending")

# Search — empty query
req("POST", "/api/search", {"query": ""}, expect=400)

# Search — query too long
req("POST", "/api/search", {"query": "x" * 201}, expect=400)

# Shopping lists CRUD
r = req("POST", "/api/lists", {"name": "Test List", "items": ["კარაქი", "კვერცხი"]}, expect=201)
list_id = r["id"] if r else None
req("GET", "/api/lists")
if list_id:
    req("GET", f"/api/lists/{list_id}")
    r2 = req("POST", f"/api/lists/{list_id}/items", {"product_name": "პური"}, expect=201)
    item_id = r2["id"] if r2 else None
    if item_id:
        req("PATCH", f"/api/lists/{list_id}/items/{item_id}", {"checked": True})
        req("PATCH", f"/api/lists/{list_id}/items/{item_id}", {"frequent": True})
        req("DELETE", f"/api/lists/{list_id}/items/{item_id}")
    req("DELETE", f"/api/lists/{list_id}")
    req("GET", f"/api/lists/{list_id}", expect=404)

# Alerts CRUD
r = req("POST", "/api/alerts", {"product_name": "ჰაგისი", "target_price": 25.0}, expect=201)
alert_id = r["id"] if r else None
req("GET", "/api/alerts")
if alert_id:
    req("PATCH", f"/api/alerts/{alert_id}", {"active": False})
    req("GET", "/api/alerts/check")
    req("DELETE", f"/api/alerts/{alert_id}")

# Basket — validation errors
req("POST", "/api/basket", {"items": []}, expect=400)
req("POST", "/api/basket", {}, expect=400)

# Crawler status
req("GET", "/api/crawler/status")

print()
print("=" * 50)
print(f"  Results: {OK} passed, {FAIL} failed")
print("=" * 50)
sys.exit(0 if FAIL == 0 else 1)
