"""
Pharmadepot.ge scraper — same Next.js SSR platform as GPC.ge.
Supports discounted prices via text-oldprice elements.
"""
import re
import httpx
from .base import BaseScraper, ProductResult, REQUEST_TIMEOUT, HEADERS


class PharmadepotScraper(BaseScraper):
    store_name = "Pharmadepot"
    base_url   = "https://pharmadepot.ge"

    def _search(self, query: str) -> list[ProductResult]:
        r = httpx.get(
            f"{self.base_url}/search",
            params={"keyword": query},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        if r.status_code != 200:
            return []
        return _parse(r.text)


def _parse(html: str) -> list[ProductResult]:
    # <a hrefLang="..." href="/ka/details/...?product=ID">
    #   <img alt="{name}" ...>
    #   <div ... content="{price}">N.NN<span itemProp="priceCurrency">₾</span></div>
    #   <div class="...text-oldprice...">N.NN<!-- -->₾</div>  (optional)
    # </a>

    card_re = re.compile(
        r'<a[^>]+hrefLang[^>]+href="(/[^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    price_re = re.compile(
        r'content="([\d\.]+)"[^>]*>[\d\.]+<span[^>]*itemProp="priceCurrency">₾'
    )
    old_re = re.compile(
        r'class="[^"]*text-oldprice[^"]*"[^>]*>([\d\.]+)<!--'
    )
    name_re = re.compile(r'<img[^>]+alt="([^"]{3,120})"')

    results = []
    for m in card_re.finditer(html):
        href, card_html = m.group(1), m.group(2)

        price_m = price_re.search(card_html)
        if not price_m:
            continue
        try:
            price = float(price_m.group(1))
        except ValueError:
            continue

        name_m = name_re.search(card_html)
        if not name_m:
            continue
        name = name_m.group(1).strip()
        if not name:
            continue

        old_m = old_re.search(card_html)
        original = None
        discount = None
        if old_m:
            try:
                original = float(old_m.group(1))
                if original > price:
                    discount = round((1 - price / original) * 100, 1)
            except ValueError:
                pass

        url = "https://pharmadepot.ge" + href
        results.append(ProductResult(
            store_name="Pharmadepot",
            product_name=name,
            current_price=price,
            original_price=original,
            discount_percent=discount,
            product_url=url,
            image_url=None,
            in_stock=True,
        ))

    return results
