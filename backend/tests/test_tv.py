"""ArchieTV (D129)."""

from datetime import timedelta

from app.adapters import youtube as yt
from app.adapters.cache import FileCache

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
 <title>Serie A</title>
 <entry>
  <yt:videoId>abc123</yt:videoId>
  <title>Highlights | Inter-Milan 2-1</title>
  <published>2026-10-20T21:00:00+00:00</published>
  <media:group><media:thumbnail url="https://i.ytimg.com/vi/abc123/hqdefault.jpg" width="480" height="360"/></media:group>
 </entry>
 <entry>
  <yt:videoId>def456</yt:videoId>
  <title>Top goals</title>
  <published>2026-10-19T10:00:00+00:00</published>
 </entry>
</feed>"""


def test_parse_feed():
    [a, b] = yt.parse_feed(FEED, "Serie A")
    assert (a.video_id, a.title, a.channel) == ("abc123", "Highlights | Inter-Milan 2-1", "Serie A")
    assert a.thumbnail.endswith("abc123/hqdefault.jpg") and b.thumbnail.endswith("def456/hqdefault.jpg")


def test_adapter_caches_feed(tmp_path):
    calls = []
    adapter = yt.YouTubeAdapter(FileCache(tmp_path, "youtube"), http_get=lambda url: calls.append(url) or FEED)
    assert len(adapter.latest("UCBJeMCIeLQos7wacox4hmLQ")) == 2
    adapter.latest("UCBJeMCIeLQos7wacox4hmLQ", timedelta(hours=1))
    assert len(calls) == 1 and "channel_id=UCBJeMCIeLQos7wacox4hmLQ" in calls[0]


def test_tv_api_sorts_and_skips_broken_channels(logged_client, monkeypatch):
    def fake_latest(self, channel_id, max_age=timedelta(hours=1)):
        if channel_id == "UCG5qGWdu8nIRZqJ_GgDwQ-w":
            raise OSError("feed giù")
        return yt.parse_feed(FEED, yt.CHANNELS[channel_id]) if channel_id == "UCBJeMCIeLQos7wacox4hmLQ" else []

    monkeypatch.setattr(yt.YouTubeAdapter, "latest", fake_latest)
    videos = logged_client.get("/api/tv").json()
    assert [v["video_id"] for v in videos] == ["abc123", "def456"]
