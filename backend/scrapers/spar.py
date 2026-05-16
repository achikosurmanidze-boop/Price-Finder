"""
Spar Georgia scraper — spar.ge
"""
from bs4 import BeautifulSoup
from .base import BaseScraper, ProductResult


class SparScraper(BaseScraper):
    store_name = "Spar"
    base_url = "https://spar.ge"
    search_url = "https://spar.ge/search"

    def _search(self, query: str) -> list[ProductResult]:
        resp = self._get(self.search_url, params={"q": query})
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        # Product cards — inspect actual HTML structure
        cards = soup.select(".product-item, .product-card, [class*='product']")
        if not cards:
            # fallback: any anchor with price
            cards = soup.select("a[href*='/product']")

        for card in cards[:10]:
            try:
                name_el = card.select_one(
                    ".product-name, .name, h2, h3, [class*='title'], [class*='name']"
                )
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)

                price_el = card.select_one(
                    ".price, .current-price, [class*='price']"
                )
                if not price_el:
                    continue
                price_text = price_el.get_text(strip=True)
                current = _parse_price(price_text)
                if not current:
                    continue

                old_el = card.select_one(".old-price, .original-price, del, s")
                original = _parse_price(old_el.get_text(strip=True)) if old_el else None
                discount = None
                if original and original > current:
                    discount = round((1 - current / original) * 100, 1)

                link = card.select_one("a")
                url = self.base_url + link["href"] if link and link.get("href", "").startswith("/") else (link["href"] if link else self.search_url)

                img = card.select_one("img")
                image_url = img.get("src") or img.get("data-src") if img else None

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


def _parse_price(text: str) -> float | None:
    import re
    cleaned = re.sub(r"[^\d.,]", "", text).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None
