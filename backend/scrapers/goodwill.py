"""Goodwill scraper — uses Goodwill's public grocery API."""

from urllib.parse import quote

from .base import BaseScraper, ProductResult


GOODWILL_TOKEN = (
    "eyJhbGciOiJSUzI1NiIsImtpZCI6IkZmVlF4dkZYcHpJMV9CX09rZjNuMFEiLCJ0eXAiOiJKV1QifQ."
    "eyJuYmYiOjE3NzkwMTkxNzQsImV4cCI6MjA5NDM3OTE3NCwiaXNzIjoiaHR0cHM6Ly9hcGkuZ29vZHdpbGwuZ2UvIiwiYXVkIjpbImh0dHBzOi8vYXBpLmdvb2R3aWxsLmdlL3Jlc291cmNlcyIsIkFwaSJdLCJjbGllbnRfaWQiOiJHcm9jZXJ5V2ViIiwic2NvcGUiOlsiR3JvY2VyeUFwaSJdfQ."
    "UXVJPo0wh6tZvADbLLc7-kwwKWTn26ikjdmxORfx7fBHYsQkT5rje6S4I_rHMkNjmIT2foZ33CBZag0THQgKv6Qi8m_PvqgBDJ57tsWun_zGYpSciKUKJF2R_EiPhMHYFEqAZnkChWpt_n95NGf4SMIhAjfumCa4RPcfoijJj3ZYmwI_8Fut3JRrOmijLDDa2Uep_VrHpNVHHjO92QhfUxoPNdw9BUJ1jvjcvhlUTXM0l2CWgZop9Nqnu0nOP80AtP2_Gg7F_5OUyJqWCDzAf0_-hpYD6pdRIX5Israj-OfXuud2w7333iFYV2hGdtT4MTOUHOkmCxYlus_G8jOEdQ"
)

GOODWILL_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ka",
    "Authorization": f"Bearer {GOODWILL_TOKEN}",
    "Origin": "https://goodwill.ge",
    "OS": "web",
    "Referer": "https://goodwill.ge/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
}


class GoodwillScraper(BaseScraper):
    store_name = "Goodwill"
    base_url = "https://goodwill.ge"
    api_url = "https://api.goodwill.ge/v1/Products"

    def _search(self, query: str) -> list[ProductResult]:
        resp = self._get(
            self.api_url,
            params={"ShopId": 1, "Name": query, "Limit": 50},
            headers=GOODWILL_HEADERS,
        )
        if resp.status_code != 200:
            return []

        results = []
        data = resp.json()

        for item in data.get("products", [])[:20]:
            try:
                name = (item.get("name") or "").strip()
                current = float(item.get("price") or 0)
                if not name or current <= 0:
                    continue

                original = item.get("previousPrice") or item.get("preSalePrice")
                original = float(original) if original else None
                discount = None
                if original and original > current:
                    discount = round((1 - current / original) * 100, 1)

                product_id = item.get("id")
                url_name = quote(name.replace("/", " "), safe="")
                product_url = f"{self.base_url}/shop/1/product/{product_id}-{url_name}"
                in_stock = (item.get("storageQuantity") or 0) > 0

                results.append(ProductResult(
                    store_name=self.store_name,
                    product_name=name,
                    current_price=current,
                    original_price=original,
                    discount_percent=discount,
                    product_url=product_url,
                    image_url=item.get("imageUrl"),
                    in_stock=in_stock,
                ))
            except Exception:
                continue

        return results
