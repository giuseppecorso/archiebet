"""Sfortuna o errore? (D113)"""

import pytest

from app.betting.autopsy import FAIR_LOSS, GOOD, LUCKY, PRICE_ERROR, UNKNOWN, UNLUCKY, VOID, SelectionFacts, autopsy


def facts(status, odds=2.0, fair=1.9, market="1X2", pick="1", sot=(7, 2)):
    return SelectionFacts(market, pick, odds, status, fair, sot[0], sot[1], 0, 1)


def test_verdicts():
    assert autopsy(facts("won")).verdict == GOOD  # 2,00 contro giusta 1,90
    assert autopsy(facts("won", fair=2.2)).verdict == LUCKY
    assert autopsy(facts("lost")).verdict == UNLUCKY  # prezzo buono e 7 tiri in porta contro 2
    assert autopsy(facts("lost", sot=(3, 4))).verdict == FAIR_LOSS
    assert autopsy(facts("lost", fair=2.2)).verdict == PRICE_ERROR
    assert autopsy(facts("void")).verdict == VOID
    assert autopsy(facts("lost", fair=None)).verdict == UNKNOWN


def test_numbers_and_markets_without_shots_logic():
    a = autopsy(facts("lost", odds=2.1, fair=2.0, market="OU2.5", pick="over"))
    assert a.verdict == FAIR_LOSS  # sui gol i tiri in porta non dicono chi "meritava"
    assert a.probability == pytest.approx(0.5) and a.clv == pytest.approx(0.05)
    assert "50%" in a.text
    away = autopsy(facts("lost", pick="X2", sot=(1, 5)))
    assert away.verdict == UNLUCKY
