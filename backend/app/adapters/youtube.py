"""ArchieTV (D129): ultimi video dei canali YouTube ufficiali delle leghe, dal feed RSS pubblico (niente chiavi, niente costi).

I video si guardano dentro l'app con il lettore ufficiale di YouTube (youtube-nocookie.com): niente download né copie.
"""

import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.adapters.base import DataSourceAdapter
from app.adapters.cache import FileCache

SOURCE = "youtube"
FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
USER_AGENT = "ArchieBet/1.0 (uso privato)"

# Canali ufficiali verificati il 2026-10-21 (Serie B e Serie C non hanno un canale ufficiale con video nel feed)
CHANNELS = {
    "UCBJeMCIeLQos7wacox4hmLQ": "Serie A",
    "UCG5qGWdu8nIRZqJ_GgDwQ-w": "Premier League",
    "UCTv-XvfzLX3i4IGWAm4sbmA": "LaLiga",
    "UC6UL29enLNe4mqwTfAyeNuw": "Bundesliga",
    "UCQsH5XtIc9hONE1BQjucM0g": "Ligue 1",
    "UCyGa1YEx9ST66rYrJTGIKOw": "UEFA",
}

NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "media": "http://search.yahoo.com/mrss/"}


@dataclass(frozen=True)
class Video:
    video_id: str
    title: str
    channel: str
    published: datetime
    thumbnail: str


def parse_feed(xml_text: str, channel: str) -> list[Video]:
    root = ET.fromstring(xml_text)
    out = []
    for entry in root.findall("a:entry", NS):
        vid = entry.findtext("yt:videoId", namespaces=NS)
        title = entry.findtext("a:title", namespaces=NS)
        published = entry.findtext("a:published", namespaces=NS)
        thumb = entry.find("media:group/media:thumbnail", NS)
        if not vid or not title or not published:
            continue
        out.append(Video(vid, title, channel, datetime.fromisoformat(published), thumb.get("url") if thumb is not None else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"))
    return out


class YouTubeAdapter(DataSourceAdapter):
    source = SOURCE

    def __init__(self, cache: FileCache, on_call: Callable[[str], None] | None = None, http_get: Callable[[str], str] | None = None):
        super().__init__(cache, on_call)
        self._http_get = http_get or _http_get

    def latest(self, channel_id: str, max_age: timedelta = timedelta(hours=1)) -> list[Video]:
        """Gli ultimi ~15 video del canale (feed in cache un'ora)."""
        body = self.cached(f"feed?{channel_id}", max_age, lambda: self._http_get(FEED_URL.format(channel_id)))
        return parse_feed(body, CHANNELS.get(channel_id, channel_id))


def _http_get(url: str) -> str:
    import httpx2

    response = httpx2.get(url, headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True)
    response.raise_for_status()
    return response.text
