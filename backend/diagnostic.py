"""
საიტის დიაგნოსტიკა — გაშვება: py diagnostic.py
ამოწმებს რომელი ქართული მაღაზია ხელმისაწვდომია სქრეიპინგისთვის.
"""
import sys
import time
import httpx

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ka-GE,ka;q=0.9,en;q=0.8",
}

SITES = [
    # (name, test_url, search_param, expect_json)
    ("Carrefour",  "https://carrefour.ge/api/2.0/catalog/product/search/", {"q":"კარაქი","page_size":3}, True),
    ("Spar",       "https://spar.ge/search",                               {"q":"კარაქი"},              False),
    ("Nikora",     "https://nikora.ge/search",                             {"q":"კარაქი"},              False),
    ("Smart",      "https://smart.ge/search",                              {"q":"კარაქი"},              False),
    ("Goodwill",   "https://goodwill.ge/search",                           {"q":"კარაქი"},              False),
    ("GPC",        "https://gpc.ge/search",                                {"q":"ამოქსიცილინი"},        False),
    ("Aversi",     "https://aversi.ge/search",                             {"q":"ამოქსიცილინი"},        False),
    ("PSP",        "https://psp.ge/search",                                {"q":"ამოქსიცილინი"},        False),
    ("Ili",        "https://ili.ge/search",                                {"q":"ამოქსიცილინი"},        False),
]

TIMEOUT = 8

def test_site(name, url, params, expect_json):
    start = time.time()
    try:
        r = httpx.get(url, params=params, headers=HEADERS,
                      timeout=TIMEOUT, follow_redirects=True)
        elapsed = time.time() - start

        if r.status_code == 200:
            if expect_json:
                try:
                    data = r.json()
                    count = len(data.get("results", data.get("data", data.get("products", []))))
                    return "OK", elapsed, f"JSON OK, {count} results"
                except Exception:
                    return "WARN", elapsed, "Status 200 but not valid JSON"
            else:
                size = len(r.text)
                # Check if it looks like real content or a block page
                has_products = any(kw in r.text.lower() for kw in
                    ["price", "ფასი", "product", "item", "₾", "gel"])
                if size < 2000:
                    return "BLOCK", elapsed, f"Response too small ({size}b) — probably blocked"
                if not has_products:
                    return "WARN", elapsed, f"No product keywords found ({size}b)"
                return "OK", elapsed, f"HTML OK ({size//1024}kb)"

        elif r.status_code in (403, 429):
            return "BLOCK", time.time()-start, f"HTTP {r.status_code} — blocked/rate-limited"
        elif r.status_code == 404:
            return "WARN", elapsed, f"HTTP 404 — search URL may have changed"
        else:
            return "WARN", elapsed, f"HTTP {r.status_code}"

    except httpx.ConnectTimeout:
        return "TIMEOUT", TIMEOUT, "Connection timeout"
    except httpx.ReadTimeout:
        return "TIMEOUT", TIMEOUT, "Read timeout"
    except httpx.ConnectError as e:
        return "ERROR", time.time()-start, f"Connection failed: {e}"
    except Exception as e:
        return "ERROR", time.time()-start, str(e)


def main():
    print("\n" + "=" * 60)
    print("  Georgian Price Finder — Site Diagnostic")
    print("=" * 60)
    print(f"  Testing {len(SITES)} sites with {TIMEOUT}s timeout each...")
    print("=" * 60 + "\n")

    working = []
    blocked = []
    failed  = []

    for name, url, params, expect_json in SITES:
        sys.stdout.write(f"  Testing {name:<12} ... ")
        sys.stdout.flush()

        status, elapsed, detail = test_site(name, url, params, expect_json)

        icon = {"OK":"✓", "WARN":"?", "BLOCK":"✗", "TIMEOUT":"⏱", "ERROR":"✗"}.get(status, "?")
        print(f"{icon}  [{elapsed:.1f}s]  {detail}")

        if status == "OK":
            working.append((name, elapsed))
        elif status in ("BLOCK", "TIMEOUT", "ERROR"):
            if elapsed >= TIMEOUT - 0.2:
                failed.append((name, "TIMEOUT"))
            else:
                blocked.append((name, detail))
        else:
            # WARN — marginal, include but flag
            working.append((name, elapsed))

    print("\n" + "=" * 60)
    print(f"  WORKING ({len(working)}): {', '.join(n for n,_ in working)}")
    print(f"  BLOCKED ({len(blocked)}): {', '.join(n for n,_ in blocked)}")
    print(f"  TIMEOUT ({len(failed)}): {', '.join(n for n,_ in failed)}")
    print("=" * 60)

    if working:
        print("\n  Fastest to slowest:")
        for name, t in sorted(working, key=lambda x: x[1]):
            bar = "█" * int(t * 3)
            print(f"    {name:<12} {t:.1f}s  {bar}")

    # Write result to a file so main.py can read it
    import json, os
    out = {
        "working": [n for n,_ in working],
        "blocked": [n for n,_ in blocked],
        "failed":  [n for n,_ in failed],
    }
    out_path = os.path.join(os.path.dirname(__file__), "site_status.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved to site_status.json")
    print("  Now run start.bat — it will use only working sites.\n")


if __name__ == "__main__":
    main()
