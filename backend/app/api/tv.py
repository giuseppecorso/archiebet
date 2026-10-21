"""ArchieTV (D129): highlights e video dei canali ufficiali delle leghe."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.adapters.cache import FileCache
from app.adapters.youtube import CHANNELS, YouTubeAdapter
from app.auth.deps import CurrentUser
from app.config import get_settings

router = APIRouter(prefix="/api/tv", tags=["archietv"])

PER_CHANNEL = 8


class VideoOut(BaseModel):
    video_id: str
    title: str
    channel: str
    published: str
    thumbnail: str


@router.get("")
def tv(_: CurrentUser) -> list[VideoOut]:
    """Ultimi video di ogni canale, dal più recente; un canale che non risponde si salta."""
    adapter = YouTubeAdapter(FileCache(get_settings().data_cache_dir, "youtube"))
    videos = []
    for channel_id in CHANNELS:
        try:
            videos += adapter.latest(channel_id)[:PER_CHANNEL]
        except Exception:  # feed non raggiungibile: gli altri canali restano
            continue
    videos.sort(key=lambda v: v.published, reverse=True)
    return [VideoOut(video_id=v.video_id, title=v.title, channel=v.channel, published=v.published.isoformat(), thumbnail=v.thumbnail) for v in videos]
