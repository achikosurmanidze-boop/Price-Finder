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
- Keep ALL results from the raw data (do not drop any store).
- Results must be ordered cheapest first by current_price.
- discount_percent and original_price may be null.
- summary must be in Georgian language.
- If no results, return empty results array and explain in summary why."""


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
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": 2048,
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


def run_agent(query: str) -> dict:
    """
    Returns {"results": [...], "summary": "..."}.
    Target: ≤ 15 seconds total.
    """
    print(f"\n[agent] Searching: {query!r}")

    # Step 1: parallel scraping
    raw = _scrape_all_parallel(query)
    print(f"[agent] Total raw results: {len(raw)}")

    if not raw:
        # No scraper returned anything — Claude gives a helpful message
        no_result_text = _call_claude(
            f'The query was: "{query}". No Georgian store returned results. '
            f'Return JSON: {{"results":[],"summary":"<Georgian explanation that product was not found, suggest alternatives>"}}'
        )
        return _extract_json(no_result_text)

    # Step 2: single Claude call to rank + summarize
    # Send at most 30 results to keep the prompt short and Claude fast
    payload = json.dumps(raw[:30], ensure_ascii=False, indent=None)
    prompt = RANK_PROMPT.format(query=query) + f"\n\nRaw results:\n{payload}"

    text = _call_claude(prompt)
    result = _extract_json(text)

    # Guarantee sort order (Claude should do it, but double-check)
    result["results"].sort(key=lambda x: x.get("current_price") or float("inf"))
    return result
