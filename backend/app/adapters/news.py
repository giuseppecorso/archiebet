"""Notizie della Serie C da feed RSS pubblici (D102): TuttoC.com e Google News.

Si leggono solo titolo, riassunto, link e data (uso privato): niente pagine intere. L'XML lo legge expat, che dalla
versione 2.4 blocca le espansioni di entità malevole ("billion laughs").
"""

import html
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode

from app.adapters.base import DataSourceAdapter
from app.adapters.cache import FileCache

SOURCE = "news"
TUTTOC_URL = "https://www.tuttoc.com/rss/"
GNEWS_URL = "https://news.google.com/rss/search"
USER_AGENT = "Mozilla/5.0 (ArchieBet, uso privato)"
SUMMARY_CHARS = 400

_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class FeedItem:
    source: str
    url: str
    title: str
    summary: str
    published_at: datetime


def _text(raw: str | None) -> str:
    """Testo pulito: senza tag HTML, entità decodificate, spazi normalizzati."""
    return " ".join(html.unescape(_TAG.sub(" ", raw or "")).split())


def parse_rss(xml_text: str, source: str) -> list[FeedItem]:
    root = ET.fromstring(xml_text)
    out = []
    for item in root.iter("item"):
        url, title, date = item.findtext("link"), _text(item.findtext("title")), item.findtext("pubDate")
        if not url or not title or not date:
            continue
        try:
            published = parsedate_to_datetime(date).astimezone(UTC)
        except (TypeError, ValueError):
            continue
        # Google News nel riassunto ha solo il link alla notizia: il titolo basta
        summary = "" if source == "gnews" else _text(item.findtext("description"))[:SUMMARY_CHARS]
        out.append(FeedItem(source, url.strip(), title[:500], summary, published))
    return out


def gnews_query(team: str) -> str:
    return f'"{team}" calcio'


class NewsAdapter(DataSourceAdapter):
    source = SOURCE

    def __init__(self, cache: FileCache, on_call: Callable[[str], None] | None = None, http_get: Callable[[str], str] | None = None):
        super().__init__(cache, on_call)
        self._http_get = http_get or _http_get

    def tuttoc(self, max_age: timedelta = timedelta(minutes=50)) -> list[FeedItem]:
        """Ultime notizie della Serie C da TuttoC.com (circa 20, cioè le ultime 6-7 ore)."""
        return parse_rss(self.cached("tuttoc", max_age, lambda: self._http_get(TUTTOC_URL)), "tuttoc")

    def google_news(self, team: str, max_age: timedelta = timedelta(hours=20)) -> list[FeedItem]:
        """Titoli di Google News sulla squadra (fino a 100, anche di altri sport: li scarta l'AI)."""
        url = f"{GNEWS_URL}?{urlencode({'q': gnews_query(team), 'hl': 'it', 'gl': 'IT', 'ceid': 'IT:it'})}"
        return parse_rss(self.cached(f"gnews?{team}", max_age, lambda: self._http_get(url)), "gnews")


def _http_get(url: str) -> str:
    import httpx2

    response = httpx2.get(url, headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return response.text
