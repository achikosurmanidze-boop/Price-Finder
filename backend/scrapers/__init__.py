from .extra       import ExtraScraper
from .goodwill    import GoodwillScraper
from .gpc         import GpcScraper
from .pharmadepot import PharmadepotScraper

ALL_SCRAPERS = [
    ExtraScraper(),
    GoodwillScraper(),
    GpcScraper(),
    PharmadepotScraper(),
]
