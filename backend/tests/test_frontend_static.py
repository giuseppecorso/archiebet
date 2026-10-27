def test_frontend_files_never_leave_the_dist_folder(client):
    from app.main import _dist

    if _dist is None or not (_dist / "index.html").is_file():
        return  # app non compilata: niente da servire
    assert "<app-root" in client.get("/partite/12").text or client.get("/partite/12").status_code == 200
    r = client.get("/..%2F..%2F..%2Fbackend%2F.env")
    assert "API_FOOTBALL_KEY" not in r.text and "ANTHROPIC" not in r.text  # mai fuori dalla cartella dell'app
    assert client.get("/api/non-esiste").status_code == 404
