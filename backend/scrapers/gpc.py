"""
GPC Pharmacy scraper — gpc.ge
GPC has a search API endpoint that returns JSON.
"""
import re
from .base import BaseScraper, ProductResult


class GpcScraper(BaseScraper):
    store_name = "GPC"
    base_url = "https://gpc.ge"
    search_api = "https://gpc.ge/api/products/search"

    def _search(self, query: str) -> list[ProductResult]:
        # Try JSON API first
        try:
            resp = self._get(
                self.search_api,
                params={"q": query, "per_page": 10}
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("products") or data.get("results") or data.get("data") or []
                if items:
                    return self._parse_json(items)
        except Exception:
            pass

        # Fallback: HTML scraping
        from bs4 import BeautifulSoup
        resp = self._get(f"{self.base_url}/search", params={"q": query})
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        cards = soup.select(".product, .product-card, .medicine-item, [class*='product']")

        for card in cards[:10]:
            try:
                name_el = card.select_one("h2, h3, .name, .title, [class*='name']")
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)

                price_el = card.select_one(".price, [class*='price']")
                if not price_el:
                    continue
                current = _parse_price(price_el.get_text(strip=True))
                if not current:
                    continue

                old_el = card.select_one(".old-price, del, s, [class*='old']")
                original = _parse_price(old_el.get_text(strip=True)) if old_el else None
                discount = None
                if original and original > current:
                    discount = round((1 - current / original) * 100, 1)

                link = card.select_one("a")
                href = link.get("href", "") if link else ""
                url = (self.base_url + href) if href.startswith("/") else (href or self.base_url)

                img = card.select_one("img")
                image_url = (img.get("src") or img.get("data-src")) if img else None

                results.append(ProductResult(
                    store_name=self.store_name,
                    product_name=name,
                    current_price=current,
                    original_price=original,
                    discount_percent=discount,
                    product_url=url,
                    image_url=image_url,
                ))
            except Exception:
                continue

        return results

    def _parse_json(self, items: list) -> list[ProductResult]:
        results = []
        for item in items[:10]:
            try:
                name = item.get("name") or item.get("title", "")
                current = float(item.get("price") or item.get("current_price") or 0)
                if not current:
                    continue
                original = item.get("old_price") or item.get("original_price")
                original = float(original) if original else None
                discount = None
                if original and original > current:
                    discount = round((1 - current / original) * 100, 1)
                slug = item.get("slug") or item.get("url", "")
                url = f"{self.base_url}/{slug}" if not slug.startswith("http") else slug
                results.append(ProductResult(
                    store_name=self.store_name,
                    product_name=name,
                    current_price=current,
                    original_price=original,
                    discount_percent=discount,
                    product_url=url,
                    image_url=item.get("image") or item.get("thumbnail"),
                    in_stock=item.get("in_stock", True),
                ))
            except Exception:
                continue
        return results


def _parse_price(text: str) -> float | None:
    cleaned = re.sub(r"[^\d.,]", "", (text or "")).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None
