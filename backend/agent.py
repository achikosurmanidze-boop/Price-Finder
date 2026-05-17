"""
Price search agent — pipeline architecture for speed.

Flow (target ≤ 15s total):
  1. All 9 scrapers run in parallel threads        (~4-7s, capped at 7s timeout)
  2. One Claude API call to rank + summarize        (~3-6s)
  3. Done.

Old approach had 9+ Claude round-trips (tool-use loop) which took 25-40s.
"""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

import httpx

from scrapers import ALL_SCRAPERS

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"   # Haiku is 3-4× faster than Sonnet for this task

SCRAPER_WALL_TIME = 8   # seconds — scrapers that don't finish in time are skipped
CLAUDE_TIMEOUT    = 30  # seconds — Claude API call hard limit

RANK_PROMPT = """You are a Georgian price comparison assistant.
Below are raw search results scraped from Georgian stores for the query: "{query}"

Analyze the results and return ONLY valid JSON (no markdown, no extra text):
{{
  "results": [
    {{
      "store_name": "...",
      "product_name": "...",
      "current_price": 0.00,
      "original_price": null,
      "discount_percent": null,
      "product_url": "...",
      "image_url": null,
      "in_stock": true
    }}
  ],
  "summary": "Short Georgian summary: cheapest option + any notable discounts. 1-2 sentences."
}}

Rules:
- IMPORTANT: Only include results that are actually relevant to the query "{query}". Remove products that have nothing to do with the search term.
- Do not keep a result just because the query appears as a flavor, scent, color, accessory, or marketing word. For drink/food brand queries such as "cola" or "coca-cola", keep beverages and food/candy, but exclude toothpaste, lip balm, cosmetics, accessories, and unrelated medical supplies unless explicitly requested.
- Results must be ordered cheapest first by current_price.
- discount_percent and original_price may be null.
- summary must be in Georgian language.
- If no relevant results found, return empty results array and explain in Georgian that the searched product was not found in the available stores."""


def _scrape_store(scraper, query: str) -> list[dict]:
    return [r.to_dict() for r in scraper.search(query)]


def _scrape_all_parallel(query: str) -> list[dict]:
    """Run all scrapers concurrently. Skip any that exceed SCRAPER_WALL_TIME.
    NOTE: pool.shutdown(wait=False) is critical — without it the ThreadPoolExecutor
    context manager blocks until every slow thread finishes, causing the 96% hang."""
    all_results: list[dict] = []

    pool = ThreadPoolExecutor(max_workers=len(ALL_SCRAPERS), thread_name_prefix="scraper")
    future_to_store = {
        pool.submit(_scrape_store, scraper, query): scraper.store_name
        for scraper in ALL_SCRAPERS
    }
    try:
        for future in as_completed(future_to_store, timeout=SCRAPER_WALL_TIME):
            store = future_to_store[future]
            try:
                results = future.result(timeout=0)
                all_results.extend(results)
                print(f"  [{store}] {len(results)} results")
            except Exception as exc:
                print(f"  [{store}] error: {exc}")
    except TimeoutError:
        done = sum(1 for f in future_to_store if f.done())
        print(f"  [wall-time] {done}/{len(ALL_SCRAPERS)} scrapers finished in {SCRAPER_WALL_TIME}s — continuing")
    finally:
        pool.shutdown(wait=False)  # abandon slow threads — do NOT block here

    return all_results


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


def _extract_json(text: str) -> dict:
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text.strip(), flags=re.MULTILINE)
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        # Try finding a JSON object anywhere in the text
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {"results": [], "summary": text}


def _has_valid_api_key() -> bool:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return key.startswith("sk-ant-") and len(key) > 40 and "ჩაწერე" not in key


def _fallback_filter_relevant(query: str, raw: list[dict]) -> list[dict]:
    """Conservative fallback for no-Claude mode; never blocks cross-language searches."""
    words = re.findall(r"[a-z0-9]+", query.lower())
    if not words:
        return raw

    matches = []
    for result in raw:
        name = (result.get("product_name") or "").lower()
        ascii_name = " ".join(re.findall(r"[a-z0-9]+", name))
        if ascii_name and all(word in ascii_name for word in words):
            matches.append(result)

    return matches or raw


def _simple_result(query: str, raw: list[dict]) -> dict:
    """Return sorted results without Claude when no API key is available."""
    raw = _fallback_filter_relevant(query, raw)
    results = sorted(raw, key=lambda x: x.get("current_price") or float("inf"))
    if results:
        cheapest = results[0]
        summary = (
            f"'{query}' — {len(results)} შედეგი. "
            f"ყველაზე იაფია {cheapest.get('store_name','')}: "
            f"{cheapest.get('current_price','')}₾"
        )
    else:
        summary = f"'{query}' — შედეგი ვერ მოიძებნა."
    return {"results": results, "summary": summary}


def run_agent(query: str) -> dict:
    """
    Returns {"results": [...], "summary": "..."}.
    Scraping always runs. Claude ranking is optional — falls back gracefully.
    """
    print(f"\n[agent] Searching: {query!r}")

    # Step 1: parallel scraping (no API key needed)
    raw = _scrape_all_parallel(query)
    print(f"[agent] Total raw results: {len(raw)}")

    if not raw:
        return {"results": [], "summary": f"'{query}' — ვერ მოიძებნა. ჩვენი მაღაზიები (Extra.ge, GPC.ge, Pharmadepot.ge) ძირითადად ფარმაციისა და სამედიცინო საქონლის სპეციალისტია."}

    # Step 2: Claude ranking (optional — skip if key missing/invalid)
    if not _has_valid_api_key():
        print("[agent] No valid API key — returning sorted results")
        return _simple_result(query, raw)

    try:
        # Balanced sample: up to 7 per store, strip image_url to keep prompt small
        by_store: dict[str, list] = {}
        for r in raw:
            by_store.setdefault(r["store_name"], []).append(r)
        balanced = [r for store_items in by_store.values() for r in store_items[:7]]
        slim = [{k: v for k, v in r.items() if k != "image_url"} for r in balanced]
        payload = json.dumps(slim, ensure_ascii=False, indent=None)
        prompt = RANK_PROMPT.format(query=query) + f"\n\nRaw results:\n{payload}"
        text = _call_claude(prompt)
        result = _extract_json(text)
        result["results"].sort(key=lambda x: x.get("current_price") or float("inf"))
        print(f"[agent] Done — {len(result.get('results', []))} results")
        return result
    except Exception as exc:
        print(f"[agent] Claude failed ({exc}) — returning sorted results")
        return _simple_result(query, raw)
