"""Archie tifoso: notizie simili raggruppate nella pagina partita (D134)."""


def test_similar_news_grouped_in_one_line():
    """Nove notizie su "Spalletti in bilico" diventano una riga; Conceição e Conceicao sono la stessa persona."""
    from datetime import UTC, datetime, timedelta

    from app.api.fan import FactOut, group_facts

    t0 = datetime(2026, 10, 21, 12, tzinfo=UTC)

    def fact(hours, kind, player, detail):
        return FactOut(team_id=1, kind=kind, label=kind, player=player, detail=detail, published_at=t0 - timedelta(hours=hours), url="u", source="gnews")

    facts = [
        fact(5, "allenatore_in_bilico", "Spalletti", "a rischio esonero"),
        fact(1, "allenatore_in_bilico", None, "si valutano alternative"),
        fact(9, "allenatore_in_bilico", "Luciano Spalletti", "vicino all'esonero"),
        fact(2, "assente", "Conceição", "spalla lussata"),
        fact(3, "assente", "Conceicao", "tempi da valutare"),
        fact(4, "assente", "Vlahovic", "out una settimana"),
    ]
    out = group_facts(facts)
    assert [(f.kind, f.detail, len(f.similar)) for f in out] == [
        ("allenatore_in_bilico", "si valutano alternative", 2),  # resta la più recente
        ("assente", "spalla lussata", 1),
        ("assente", "out una settimana", 0),
    ]
    assert out[0].similar[0].detail == "a rischio esonero"  # le altre dalla più recente
