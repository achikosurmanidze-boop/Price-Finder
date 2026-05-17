"""
Base scraper — reduced timeout and no artificial delay
(each store gets exactly 1 request per search, so no need to throttle).
"""
import httpx

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ka-GE,ka;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Hard cap per scraper — if it doesn't respond in 7s, skip it
REQUEST_TIMEOUT = 7


class ProductResult:
    __slots__ = (
        "store_name", "product_name", "current_price", "original_price",
        "discount_percent", "product_url", "image_url", "in_stock",
    )

    def __init__(self, store_name, product_name, current_price,
                 original_price, discount_percent, product_url,
                 image_url, in_stock=True):
        self.store_name = store_name
        self.product_name = product_name
        self.current_price = current_price
        self.original_price = original_price
        self.discount_percent = discount_percent
        self.product_url = product_url
        self.image_url = image_url
        self.in_stock = in_stock

    def to_dict(self) -> dict:
        return {
            "store_name": self.store_name,
            "product_name": self.product_name,
            "current_price": self.current_price,
            "original_price": self.original_price,
            "discount_percent": self.discount_percent,
            "product_url": self.product_url,
            "image_url": self.image_url,
            "in_stock": self.in_stock,
        }


class BaseScraper:
    store_name: str = ""
    base_url: str = ""

    def search(self, query: str) -> list:
        """Runs _search, returns [] on any error — never raises."""
        try:
            return self._search(query)
        except Exception as exc:
            print(f"[{self.store_name}] error: {type(exc).__name__}: {exc}")
            return []

    def _search(self, query: str) -> list:
        raise NotImplementedError

    def _get(self, url: str, params: dict = None, headers: dict = None):
        return httpx.get(
            url, params=params, headers=headers or HEADERS,
            timeout=REQUEST_TIMEOUT, follow_redirects=True,
        )
