"""Stemmi e loghi (D84): salvati al primo uso, "non esiste" ricordato, niente stemma senza codice API-Football."""

from app.api import media
from app.models import Team, TeamAlias


def test_media_file_downloads_once_and_remembers_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "get_settings", lambda: type("S", (), {"data_cache_dir": tmp_path})())
    calls = []

    def fake(url):
        calls.append(url)
        return None if url.endswith("/999.png") else b"PNG"

    assert media.media_file("teams", 494, fake).read_bytes() == b"PNG"
    assert media.media_file("teams", 494, fake) is not None
    assert media.media_file("teams", 999, fake) is None
    assert media.media_file("teams", 999, fake) is None
    assert calls == ["https://media.api-sports.io/football/teams/494.png", "https://media.api-sports.io/football/teams/999.png"]


def test_team_logo_needs_api_football_code(client, logged_client, db, tmp_path, monkeypatch):
    monkeypatch.setattr(media, "get_settings", lambda: type("S", (), {"data_cache_dir": tmp_path})())
    monkeypatch.setattr(media, "_download", lambda url: b"PNG")
    with_code, without = Team(name="Udinese", country="Italia"), Team(name="Monza", country="Italia")
    db.add_all([with_code, without])
    db.flush()
    db.add(TeamAlias(team_id=with_code.id, source="api-football", alias="494"))
    db.commit()

    response = logged_client.get(f"/api/media/team/{with_code.id}.png")
    assert response.status_code == 200 and response.content == b"PNG"
    assert "max-age" in response.headers["cache-control"]
    assert logged_client.get(f"/api/media/team/{without.id}.png").status_code == 404
    assert logged_client.get("/api/media/competition/ITA-A.png").status_code == 200
    assert logged_client.get("/api/media/competition/XXX.png").status_code == 404
