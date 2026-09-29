"""
Testes das consultas do dashboard contra um SQLite temporário
populado pelas mesmas funções de carga do loader.
"""

import pytest

from database import (
    connect,
    upsert_league,
    upsert_game,
    replace_markets,
    set_score,
)
from dashboard_queries import (
    list_leagues,
    list_games,
    get_game,
    get_odds,
)


def make_event(fixture_id, home, away, start_time, markets=None):
    return {
        "fixture_id": fixture_id,
        "meeting_id": "M1",
        "home_team": home,
        "away_team": away,
        "start_time": start_time,
        "markets": markets or [],
    }


MARKETS = [
    {
        "market_id": "40",
        "group_id": "G1",
        "group_key": "G1",
        "group_name": "Resultado Final",
        "market_name": "Resultado Final",
        "selections": [
            {"id": "s1", "name": "Brasil", "odds_fractional": "1/1", "odds_decimal": 2.0, "suspended": "0"},
            {"id": "s2", "name": "Empate", "odds_fractional": "2/1", "odds_decimal": 3.0, "suspended": "0"},
            {"id": "s3", "name": "Argentina", "odds_fractional": "3/1", "odds_decimal": 4.0, "suspended": "1"},
        ],
    },
    {
        "market_id": "50",
        "group_id": "G2",
        "group_key": "G2",
        "group_name": "Gols Mais/Menos",
        "market_name": "Mais de",
        "selections": [
            {"id": "s4", "name": "2.5", "handicap": "2.5", "odds_fractional": "4/5", "odds_decimal": 1.8},
        ],
    },
]


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "test.sqlite")

    with conn:
        # Mesmo nome com dois ids, como acontece nas capturas reais.
        upsert_league(conn, "L1", "Express Cup")
        upsert_league(conn, "L2", "Express Cup")
        upsert_league(conn, "L3", "Euro Cup")

        games = [
            ("L1", make_event("F1", "Brasil", "Argentina", "2026-09-28T10:00:00", MARKETS)),
            ("L2", make_event("F2", "Chile", "Peru", "2026-09-28T11:00:00")),
            ("L3", make_event("F3", "França", "Itália", "2026-09-28T09:00:00")),
        ]

        for league_id, event in games:
            upsert_game(conn, event, league_id=league_id, run_id="R1", captured_at="2026-09-28T08:00:00")
            replace_markets(conn, event["fixture_id"], event["markets"])

        set_score(conn, "F3", 2, 1)

    yield conn

    conn.close()


def test_list_leagues_returns_unique_sorted_names(conn):
    assert list_leagues(conn) == ["Euro Cup", "Express Cup"]


def test_list_games_without_filter_returns_all_newest_first(conn):
    games = list_games(conn)

    assert [g["fixture_id"] for g in games] == ["F2", "F1", "F3"]


def test_list_games_filters_by_league_name_across_ids(conn):
    games = list_games(conn, leagues=["Express Cup"])

    assert {g["fixture_id"] for g in games} == {"F1", "F2"}


def test_list_games_with_empty_filter_returns_all(conn):
    assert len(list_games(conn, leagues=[])) == 3


def test_list_games_row_shape(conn):
    game = next(g for g in list_games(conn) if g["fixture_id"] == "F3")

    assert game["confronto"] == "França x Itália"
    assert game["liga"] == "Euro Cup"
    assert game["data"] == "2026-09-28"
    assert game["hora"] == "09:00:00"
    assert game["placar"] == "2-1"


def test_get_game_returns_header(conn):
    game = get_game(conn, "F1")

    assert game["home_team"] == "Brasil"
    assert game["away_team"] == "Argentina"
    assert game["liga"] == "Express Cup"
    assert game["home_score"] is None
    assert game["run_id"] == "R1"


def test_get_game_unknown_returns_none(conn):
    assert get_game(conn, "NOPE") is None


def test_get_odds_keeps_coupon_order(conn):
    odds = get_odds(conn, "F1")

    assert [o["selection"] for o in odds] == ["Brasil", "Empate", "Argentina", "2.5"]
    assert odds[0]["group_name"] == "Resultado Final"
    assert odds[0]["odds_decimal"] == 2.0
    assert odds[2]["suspended"] == 1
    assert odds[3]["handicap"] == "2.5"


def test_get_odds_game_without_markets_is_empty(conn):
    assert get_odds(conn, "F2") == []
