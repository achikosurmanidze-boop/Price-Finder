"""
Extra.ge scraper — Angular SSR marketplace.
Requires mobile User-Agent; desktop UA returns minimal SPA shell.
"""
import re
import httpx
from .base import BaseScraper, ProductResult, REQUEST_TIMEOUT

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
)

HEADERS = {
    "User-Agent": MOBILE_UA,
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "ka-GE,ka;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}


class ExtraScraper(BaseScraper):
    store_name = "Extra.ge"
    base_url   = "https://extra.ge"

    def _search(self, query: str) -> list[ProductResult]:
        r = httpx.get(
            f"{self.base_url}/search",
            params={"q": query},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        if r.status_code != 200:
            return []
        return _parse(r.text)


def _parse(html: str) -> list[ProductResult]:
    # Product names and image URLs — each product has exactly one:
    # <img alt="Product image of {name}" src="https://sonic.ge/...">
    img_pattern = re.compile(
        r'<img[^>]+alt="Product image of ([^"]+)"[^>]+src="(https://sonic\.ge/[^"]+)"',
        re.IGNORECASE,
    )
    img_matches = img_pattern.findall(html)

    # Prices — <p ... id="productPrice_{N}"> {price} ₾ </p>
    price_pattern = re.compile(r'id="productPrice_\d+"[^>]*>\s*([\d\.]+)\s*₾')
    prices_raw = price_pattern.findall(html)

    # Product URLs — href="/product/..." (3 anchors per product, same URL)
    url_pattern = re.compile(r'href="(/product/[^"]+)"')
    seen_urls: dict[str, bool] = {}
    product_urls: list[str] = []
    for m in url_pattern.finditer(html):
        u = m.group(1)
        if u not in seen_urls:
            seen_urls[u] = True
            product_urls.append(u)

    count = min(len(img_matches), len(prices_raw), len(product_urls))
    results = []
    for i in range(count):
        name, img_url = img_matches[i]
        name = name.strip()
        try:
            price = float(prices_raw[i])
        except ValueError:
            continue
        url = "https://extra.ge" + product_urls[i]
        results.append(ProductResult(
            store_name="Extra.ge",
            product_name=name,
            current_price=price,
            original_price=None,
            discount_percent=None,
            product_url=url,
            image_url=img_url,
            in_stock=True,
        ))
    return results
