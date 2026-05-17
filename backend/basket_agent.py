"""
Basket analysis agent — pipeline architecture for speed.

Flow (target ≤ 20s total):
  1. All items × all stores scraped in parallel    (~5-8s, capped by 7s timeout)
  2. One Claude API call for full basket analysis   (~5-8s)
  3. Done.

For 3 items × 9 stores = 27 parallel HTTP calls — all finish within the wall-clock
timeout of the slowest store response.
"""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from scrapers import ALL_SCRAPERS

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"   # Sonnet for deeper basket math
SCRAPER_WALL_TIME = 8
CLAUDE_TIMEOUT    = 45

BASKET_PROMPT = """You are a Georgian price comparison assistant analyzing a shopping basket.

Items requested: {items_list}

Below are raw results from Georgian stores for each item.
Return ONLY valid JSON (no markdown, no extra text):

{{
  "per_item": [
    {{
      "item": "<original item name>",
      "cheapest_store": "StoreName",
      "cheapest_price": 5.50,
      "cheapest_url": "https://...",
      "all_stores": [
        {{"store": "Carrefour", "price": 5.50, "product_name": "...", "url": "...", "discount_percent": null}}
      ]
    }}
  ],
  "basket_comparison": [
    {{
      "store": "StoreName",
      "total": 24.50,
      "items_found": 3,
      "items_total": {n_items},
      "savings_vs_max": 5.20
    }}
  ],
  "best_single_store": "StoreName",
  "best_single_total": 24.50,
  "split_strategy": [
    {{"store": "StoreName", "items": ["item1", "item2"], "subtotal": 8.00}}
  ],
  "split_total": 22.00,
  "summary": "Georgian 2-sentence summary: best single store + split savings if significant."
}}

Rules:
- per_item: for each requested item, find the cheapest match across all stores.
- basket_comparison: for each store, sum prices of available items (use cheapest match per store).
  Include savings_vs_max = (max_total_across_stores - this_store_total).
- best_single_store: store with lowest basket_comparison total where all items are found (prefer completeness).
- split_strategy: optimal split — assign each item to its cheapest store, group by store.
  Only include if split_total < best_single_total (i.e. splitting actually saves money).
- summary must be in Georgian."""


def _scrape_store_item(scraper, query: str) -> tuple[str, str, list[dict]]:
    """Returns (store_name, query, results)."""
    results = [r.to_dict() for r in scraper.search(query)]
    return scraper.store_name, query, results


def _scrape_all_items_parallel(items: list[str]) -> dict[str, list[dict]]:
    """
    Scrape all items across all stores simultaneously.
    Returns {item: [result, ...]} — results from ALL stores merged per item.
    """
    item_results: dict[str, list[dict]] = {item: [] for item in items}

    # Build all (scraper, item) pairs
    tasks = [(scraper, item) for item in items for scraper in ALL_SCRAPERS]
    total = len(tasks)

    pool = ThreadPoolExecutor(max_workers=min(total, 36), thread_name_prefix="basket")
    futures = {
        pool.submit(_scrape_store_item, scraper, item): (scraper.store_name, item)
        for scraper, item in tasks
    }
    done = 0
    try:
        for future in as_completed(futures, timeout=SCRAPER_WALL_TIME):
            store_name, item = futures[future]
            done += 1
            try:
                _, _, results = future.result(timeout=0)
                item_results[item].extend(results)
                if results:
                    print(f"  [{store_name}] '{item}': {len(results)} results")
            except Exception as exc:
                print(f"  [{store_name}] '{item}': {type(exc).__name__}")
    except TimeoutError:
        print(f"  [wall-time] {done}/{total} basket tasks finished — continuing")
    finally:
        pool.shutdown(wait=False)

    print(f"[basket] {done}/{total} scrape tasks completed")
    return item_results


def _call_claude(prompt: str) -> str:
    resp = httpx.post(
        ANTHROPIC_API_URL,
        headers={
            "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=CLAUDE_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def _has_valid_api_key() -> bool:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return key.startswith("sk-ant-") and len(key) > 40 and "ჩაწერე" not in key


def _extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text.strip(), flags=re.MULTILINE)
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {
        "per_item": [], "basket_comparison": [],
        "best_single_store": None, "best_single_total": None,
        "split_strategy": [], "split_total": None,
        "summary": text,
    }


def run_basket_agent(items: list[str]) -> dict:
    """
    Analyze a basket of items across all Georgian stores.
    Target: ≤ 20 seconds total.
    """
    print(f"\n[basket] Items: {items}")

    # Step 1: parallel scraping of all items × all stores
    item_results = _scrape_all_items_parallel(items)

    total_results = sum(len(v) for v in item_results.values())
    print(f"[basket] Total raw results: {total_results}")

    # Step 2: build compact payload for Claude (top 5 per store per item)
    compact: dict[str, list[dict]] = {}
    for item, results in item_results.items():
        # Sort by price and keep top 5 per store to limit prompt size
        seen_stores: dict[str, list] = {}
        for r in sorted(results, key=lambda x: x.get("current_price") or 999):
            store = r["store_name"]
            if store not in seen_stores:
                seen_stores[store] = []
            if len(seen_stores[store]) < 2:  # top 2 per store per item
                seen_stores[store].append(r)
        compact[item] = [r for rs in seen_stores.values() for r in rs]

    payload = json.dumps(compact, ensure_ascii=False, indent=None)
    items_list = ", ".join(f'"{i}"' for i in items)
    prompt = BASKET_PROMPT.format(
        items_list=items_list, n_items=len(items)
    ) + f"\n\nScraped results per item:\n{payload}"

    if not _has_valid_api_key():
        print("[basket_agent] No valid API key — returning raw results")
        return {"per_item": [], "basket_comparison": [], "best_single_store": None,
                "best_single_total": None, "split_strategy": [], "split_total": None,
                "summary": "Anthropic API გასაღები არ არის დაყენებული — კალათის AI ანალიზი დროებით მიუწვდომელია."}

    try:
        text = _call_claude(prompt)
        return _extract_json(text)
    except Exception as exc:
        print(f"[basket_agent] Claude call failed ({exc}) — returning raw results")
        return {"per_item": [], "basket_comparison": [], "best_single_store": None,
                "best_single_total": None, "split_strategy": [], "split_total": None,
                "summary": "შეცდომა — სცადეთ ხელახლა."}
