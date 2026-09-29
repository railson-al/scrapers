"""
Testes do fluxo de resultados: parser -> normalizer -> loader/database.

O corpo abaixo segue o formato real de
contentdata/virtualsportscontentapi/results (seleções encurtadas).
"""

import pytest

from parser import parse_results
from normalizer import (
    normalize_results,
    parse_result_time,
    parse_correct_score,
)
from loader import infer_start_time
from database import (
    connect,
    upsert_league,
    upsert_game,
    upsert_result,
    match_results,
)


BODY = (
    "F|CL;ID=146;IT=#AVA#B146#C20120653#R^1#;|EV;|"
    "MG;ID=MEET;DO=1;SY=vet;|"
    "MG;NA=Premier League;SM=1.54;N2=City;SS=1#2;N3=Brighton;SY=avo;DO=1;|"
    "MA;SY=avr;PY=avx;|"
    "PA;EX=Resultado Final;NA=Brighton;OD=5/4;|"
    "PA;EX=Resultado Correto;NA=Brighton 2-1;OD=15/2;|"
    "PA;EX=Resultado Correto - Intervalo;NA=Empate 1-1;OD=16/1;|"
    "MG;NA=Premier League;SM=1.51;N2=Aston;SS=1#0;N3=Brentford;SY=avo;DO=1;|"
    "MA;SY=avr;PY=avx;|"
    "PA;EX=Resultado Final;NA=Aston;OD=8/5;|"
    "PA;EX=Resultado Correto - Intervalo;NA=Qualquer Outro Resultado;OD=7/1;|"
    "MG;NA=Premier League;SM=23.58;N2=Leeds;SS=#;N3=Everton;SY=avo;DO=1;|"
    "MA;SY=avr;PY=avx;|"
    "PA;EX=Resultado Final;NA=Empate;OD=9/4;|"
    "PA;EX=Resultado Correto;NA=Qualquer Outro Resultado;OD=20/1;|"
)

RAW = {
    "sequence": 69,
    "captured_at": "2026-09-29T00:25:04-03:00",
    "type": "results",
    "request": {
        "url": "https://www.bet365.bet.br/contentdata/virtualsportscontentapi/results?pd=x",
        "pd": "#AVA#B146#C20120653#R^1#",
    },
    "body": {"content": BODY, "sha256": "abc"},
}


# ============================================================
# PARSER
# ============================================================

def test_parse_results_groups_selections_per_game():
    parsed = parse_results(RAW)

    assert parsed["kind"] == "results"
    assert parsed["source"]["pd_tokens"]["C"] == "20120653"

    games = parsed["results"]

    assert [g["fields"]["N2"] for g in games] == ["City", "Aston", "Leeds"]
    assert [s["EX"] for s in games[0]["selections"]] == [
        "Resultado Final",
        "Resultado Correto",
        "Resultado Correto - Intervalo",
    ]
    assert games[0]["selections"][0]["odds_decimal"] == 2.25


def test_parse_results_keeps_all_records():
    parsed = parse_results(RAW)

    # Nada é descartado: o cabeçalho MEET fica em records.
    assert any(
        r["fields"].get("ID") == "MEET"
        for r in parsed["records"]
    )
    assert parsed["summary"]["result_count"] == 3


# ============================================================
# NORMALIZER
# ============================================================

@pytest.mark.parametrize(
    ("sm", "expected"),
    [
        ("1.54", "01:54"),
        ("23.58", "23:58"),
        ("0.05", "00:05"),
        ("1.5", None),
        ("24.00", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_result_time(sm, expected):
    assert parse_result_time(sm) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # "<vencedor> gols_vencedor-gols_perdedor"
        ("City 2-1", (2, 1)),
        ("Brighton 2-1", (1, 2)),
        ("Empate 1-1", (1, 1)),
        ("Qualquer Outro Resultado", (None, None)),
        ("Para City ganhar por qualquer outro resultado", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_correct_score(name, expected):
    assert parse_correct_score(name, "City", "Brighton") == expected


def test_normalize_results():
    normalized = normalize_results(parse_results(RAW))

    assert normalized["source"]["league_id"] == "20120653"

    city, aston, leeds = normalized["results"]

    assert city == {
        "league_name": "Premier League",
        "result_time": "01:54",
        "home_team": "City",
        "away_team": "Brighton",
        "home_score": 1,
        "away_score": 2,
        "ht_home_score": 1,
        "ht_away_score": 1,
        "winner": "away",
        "selections": [
            {"market": "Resultado Final", "name": "Brighton", "odds_fractional": "5/4", "odds_decimal": 2.25},
            {"market": "Resultado Correto", "name": "Brighton 2-1", "odds_fractional": "15/2", "odds_decimal": 8.5},
            {"market": "Resultado Correto - Intervalo", "name": "Empate 1-1", "odds_fractional": "16/1", "odds_decimal": 17.0},
        ],
    }

    assert (aston["home_score"], aston["away_score"]) == (1, 0)
    assert (aston["ht_home_score"], aston["ht_away_score"]) == (None, None)
    assert aston["winner"] == "home"

    # SS=# : placar exato desconhecido, mas o vencedor sai do Resultado Final.
    assert (leeds["home_score"], leeds["away_score"]) == (None, None)
    assert leeds["winner"] == "draw"


# ============================================================
# LOADER: DATA DO JOGO
# ============================================================

@pytest.mark.parametrize(
    ("result_time", "reference", "expected"),
    [
        ("01:54", "2026-09-29T04:24:00", "2026-09-29T01:54:00"),
        # Referência logo depois da meia-noite: o jogo foi ontem.
        ("23:58", "2026-09-29T00:10:00", "2026-09-28T23:58:00"),
        ("04:24", "2026-09-29T04:24:00", "2026-09-29T04:24:00"),
        ("01:54", None, None),
        (None, "2026-09-29T04:24:00", None),
    ],
)
def test_infer_start_time(result_time, reference, expected):
    assert infer_start_time(result_time, reference) == expected


# ============================================================
# DATABASE
# ============================================================

def make_result(**overrides):
    result = {
        "league_name": "Premier League",
        "result_time": "01:54",
        "home_team": "City",
        "away_team": "Brighton",
        "home_score": 1,
        "away_score": 2,
        "ht_home_score": 1,
        "ht_away_score": 1,
        "winner": "away",
        "selections": [],
    }
    result.update(overrides)
    return result


def save(conn, result, start_time="2026-09-29T01:54:00"):
    upsert_result(
        conn,
        result,
        league_id="L1",
        start_time=start_time,
        run_id="R2",
        captured_at="2026-09-29T00:25:04-03:00",
    )


def add_game(conn, fixture_id="F1", start_time="2026-09-29T01:54:00"):
    upsert_game(
        conn,
        {
            "fixture_id": fixture_id,
            "home_team": "City",
            "away_team": "Brighton",
            "start_time": start_time,
        },
        league_id="L1",
        run_id="R1",
        captured_at="2026-09-28T21:50:00-03:00",
    )


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "test.sqlite")
    upsert_league(conn, "L1", "Premier League Inglês - Doméstico")
    yield conn
    conn.close()


def score(conn, fixture_id):
    return tuple(
        conn.execute(
            "SELECT home_score, away_score FROM games WHERE fixture_id = ?",
            (fixture_id,),
        ).fetchone()
    )


def test_match_results_sets_score_on_exact_game(conn):
    add_game(conn, "F1", "2026-09-29T01:54:00")
    # Mesmo confronto em outro horário: não pode receber o placar.
    add_game(conn, "F0", "2026-09-28T01:54:00")
    save(conn, make_result())

    assert match_results(conn) == 1
    assert score(conn, "F1") == (1, 2)
    assert score(conn, "F0") == (None, None)

    row = conn.execute("SELECT fixture_id FROM results").fetchone()
    assert row["fixture_id"] == "F1"


SYNTHETIC_ID = "res:L1|2026-09-29T01:54:00|City|Brighton"


def test_result_without_game_creates_game_with_score(conn):
    save(conn, make_result())

    assert match_results(conn) == 1

    game = conn.execute(
        "SELECT * FROM games WHERE fixture_id = ?",
        (SYNTHETIC_ID,),
    ).fetchone()

    assert game["league_id"] == "L1"
    assert (game["home_team"], game["away_team"]) == ("City", "Brighton")
    assert game["start_time"] == "2026-09-29T01:54:00"
    assert (game["home_score"], game["away_score"]) == (1, 2)

    row = conn.execute("SELECT fixture_id FROM results").fetchone()
    assert row["fixture_id"] == SYNTHETIC_ID

    # Idempotente: não cria outro jogo nem reaplica.
    assert match_results(conn) == 0
    assert conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1


def test_real_game_loaded_later_replaces_synthetic(conn):
    save(conn, make_result())
    match_results(conn)

    add_game(conn)

    assert match_results(conn) == 1
    assert score(conn, "F1") == (1, 2)

    fixtures = [row[0] for row in conn.execute("SELECT fixture_id FROM games")]
    assert fixtures == ["F1"]
    assert conn.execute("SELECT fixture_id FROM results").fetchone()[0] == "F1"


def test_result_creates_league_if_missing(conn):
    upsert_result(
        conn,
        make_result(),
        league_id="NEW",
        start_time="2026-09-29T01:54:00",
        run_id="R2",
        captured_at="2026-09-29T00:25:04-03:00",
    )

    assert match_results(conn) == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM leagues WHERE league_id = 'NEW'"
    ).fetchone()[0] == 1


def test_result_without_start_time_is_kept_but_not_matched(conn):
    add_game(conn)
    save(conn, make_result(), start_time=None)

    assert match_results(conn) == 0
    assert score(conn, "F1") == (None, None)
    assert conn.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 1


def test_unknown_score_links_game_without_score(conn):
    add_game(conn)
    save(conn, make_result(home_score=None, away_score=None))

    assert match_results(conn) == 0
    assert score(conn, "F1") == (None, None)
    assert conn.execute("SELECT fixture_id FROM results").fetchone()[0] == "F1"


def test_reloading_same_result_is_idempotent(conn):
    add_game(conn)
    save(conn, make_result())
    save(conn, make_result())

    assert conn.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 1
    assert match_results(conn) == 1
    # Já aplicado: nada a fazer na segunda vez.
    assert match_results(conn) == 0


def test_reloading_game_keeps_score(conn):
    add_game(conn)
    save(conn, make_result())
    match_results(conn)

    add_game(conn)

    assert score(conn, "F1") == (1, 2)


# ============================================================
# LOADER: COUPON FORA DO PADRÃO
# ============================================================

def test_load_file_skips_event_without_teams(conn, tmp_path):
    import json

    from loader import load_file

    # Coupon que veio em inglês: o normalizer não acha os times.
    coupon = tmp_path / "20260929_092928" / "0003_coupon.json"
    coupon.parent.mkdir()
    coupon.write_text(
        json.dumps(
            {
                "source": {"captured_at": "2026-09-29T09:29:40-03:00", "pd": "#AC#B146#C20940364#M20940364#"},
                "events": [
                    {"fixture_id": "BAD", "home_team": None, "away_team": None, "start_time": "2026-09-29T13:30:00", "markets": []},
                    {"fixture_id": "OK", "home_team": "City", "away_team": "Brighton", "start_time": "2026-09-29T13:31:00", "markets": []},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert load_file(conn, coupon, {}) == 1

    fixtures = [row[0] for row in conn.execute("SELECT fixture_id FROM games")]
    assert fixtures == ["OK"]
