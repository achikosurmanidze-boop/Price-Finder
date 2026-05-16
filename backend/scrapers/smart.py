"""
Smart supermarket scraper — smart.ge
"""
import re
from bs4 import BeautifulSoup
from .base import BaseScraper, ProductResult


def _parse_price(text: str) -> float | None:
    cleaned = re.sub(r"[^\d.,]", "", (text or "")).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


class SmartScraper(BaseScraper):
    store_name = "Smart"
    base_url = "https://smart.ge"
    search_url = "https://smart.ge/search"

    def _search(self, query: str) -> list[ProductResult]:
        resp = self._get(self.search_url, params={"q": query})
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        cards = soup.select(".product, .product-card, .product-item, [class*='product']")

        for card in cards[:10]:
            try:
                name_el = card.select_one("h2, h3, .product-name, .name, [class*='title']")
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)

                price_el = card.select_one(".price, .current-price, [class*='price']")
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
                url = (self.base_url + href) if href.startswith("/") else (href or self.search_url)

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
