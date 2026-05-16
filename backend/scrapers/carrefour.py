"""
Carrefour Georgia scraper — carrefour.ge
Uses their JSON search API endpoint.
"""
import re
from .base import BaseScraper, ProductResult


class CarrefourScraper(BaseScraper):
    store_name = "Carrefour"
    base_url = "https://carrefour.ge"
    search_api = "https://carrefour.ge/api/2.0/catalog/product/search/"

    def _search(self, query: str) -> list[ProductResult]:
        resp = self._get(self.search_api, params={"q": query, "page_size": 10})
        if resp.status_code != 200:
            return []

        data = resp.json()
        results = []

        for item in data.get("results", []):
            try:
                name = item.get("name", "")
                slug = item.get("slug", "")
                url = f"{self.base_url}/{slug}"

                price_info = item.get("price", {})
                current = float(price_info.get("current_price") or 0)
                original = price_info.get("old_price")
                original = float(original) if original else None

                discount = None
                if original and original > current:
                    discount = round((1 - current / original) * 100, 1)

                image = item.get("image") or item.get("thumbnail")

                if current > 0:
                    results.append(ProductResult(
                        store_name=self.store_name,
                        product_name=name,
                        current_price=current,
                        original_price=original,
                        discount_percent=discount,
                        product_url=url,
                        image_url=image,
                        in_stock=item.get("in_stock", True),
                    ))
            except (KeyError, TypeError, ValueError):
                continue

        return results
