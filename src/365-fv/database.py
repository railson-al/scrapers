"""
Camada de database (SQLite em dev) compartilhada pelos scripts.

O schema fica em schema.sql, ao lado deste arquivo, e é aplicado
a cada conexão (é idempotente).
"""

import json
import sqlite3

from pathlib import Path

from config import DB_PATH
from utils import now_iso


SCHEMA_PATH = Path(__file__).with_name(
    "schema.sql"
)


# ============================================================
# CONEXÃO
# ============================================================

def connect(
    path: Path = DB_PATH,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = sqlite3.connect(
        path
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA foreign_keys = ON"
    )

    conn.execute(
        "PRAGMA journal_mode = WAL"
    )

    conn.executescript(
        SCHEMA_PATH.read_text(
            encoding="utf-8"
        )
    )

    return conn


# ============================================================
# HELPERS
# ============================================================

def to_int(value):
    if value is None or value == "":
        return None

    try:
        return int(value)

    except (TypeError, ValueError):
        return None


# ============================================================
# LIGAS
# ============================================================

def upsert_league(
    conn,
    league_id: str,
    name: str | None,
):
    # Nome nulo não apaga um nome já conhecido.
    conn.execute(
        """
        INSERT INTO leagues (league_id, name)
        VALUES (?, ?)
        ON CONFLICT(league_id) DO UPDATE SET
            name = COALESCE(excluded.name, leagues.name)
        """,
        (
            league_id,
            name,
        ),
    )


# ============================================================
# JOGOS
# ============================================================

def upsert_game(
    conn,
    event: dict,
    league_id: str | None,
    run_id: str,
    captured_at: str,
):
    """
    Insere/atualiza o jogo sem tocar no placar:
    home_score/away_score só mudam via set_score().
    """

    conn.execute(
        """
        INSERT INTO games (
            fixture_id, league_id, meeting_id,
            home_team, away_team, start_time,
            run_id, captured_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fixture_id) DO UPDATE SET
            league_id   = COALESCE(excluded.league_id, games.league_id),
            meeting_id  = COALESCE(excluded.meeting_id, games.meeting_id),
            home_team   = excluded.home_team,
            away_team   = excluded.away_team,
            start_time  = excluded.start_time,
            run_id      = excluded.run_id,
            captured_at = excluded.captured_at,
            updated_at  = excluded.updated_at
        """,
        (
            event["fixture_id"],
            league_id,
            event.get("meeting_id"),
            event["home_team"],
            event["away_team"],
            event["start_time"],
            run_id,
            captured_at,
            now_iso(),
        ),
    )


def set_score(
    conn,
    fixture_id: str,
    home_score: int,
    away_score: int,
):
    # Gancho para o futuro coletor de resultados.
    conn.execute(
        """
        UPDATE games
        SET home_score = ?,
            away_score = ?,
            updated_at = ?
        WHERE fixture_id = ?
        """,
        (
            home_score,
            away_score,
            now_iso(),
            fixture_id,
        ),
    )


# ============================================================
# MERCADOS / ODDS
# ============================================================

def replace_markets(
    conn,
    fixture_id: str,
    markets: list,
):
    """
    Troca os mercados do jogo pelo snapshot mais recente.
    O ON DELETE CASCADE remove as seleções antigas.

    Retorna (mercados, seleções) inseridos.
    """

    conn.execute(
        "DELETE FROM markets WHERE fixture_id = ?",
        (
            fixture_id,
        ),
    )

    selection_count = 0

    for position, market in enumerate(markets):

        cursor = conn.execute(
            """
            INSERT INTO markets (
                fixture_id, position, market_id,
                group_id, group_key, group_name, market_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fixture_id,
                position,
                market.get("market_id"),
                market.get("group_id"),
                market.get("group_key"),
                market.get("group_name"),
                market.get("market_name"),
            ),
        )

        market_pk = cursor.lastrowid

        rows = [
            (
                market_pk,
                selection_position,
                selection["id"],
                selection.get("name"),
                selection.get("label"),
                selection.get("handicap"),
                selection.get("odds_fractional"),
                selection.get("odds_decimal"),
                to_int(
                    selection.get("suspended")
                ),
            )
            for selection_position, selection in enumerate(
                market.get("selections") or []
            )
        ]

        conn.executemany(
            """
            INSERT INTO selections (
                market_pk, position, selection_id,
                name, label, handicap,
                odds_fractional, odds_decimal, suspended
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

        selection_count += len(rows)

    return (
        len(markets),
        selection_count,
    )


# ============================================================
# RESULTADOS
# ============================================================

def upsert_result(
    conn,
    result: dict,
    league_id: str,
    start_time: str | None,
    run_id: str,
    captured_at: str,
):
    """
    Grava um resultado da aba Resultados. O
    casamento com games fica em match_results(),
    para valer também para jogos carregados
    depois do resultado.
    """

    result_key = "|".join(
        (
            league_id,
            start_time or result["result_time"],
            result["home_team"],
            result["away_team"],
        )
    )

    conn.execute(
        """
        INSERT INTO results (
            result_key, league_id, home_team, away_team,
            result_time, start_time,
            home_score, away_score, ht_home_score, ht_away_score,
            winner, selections,
            run_id, captured_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(result_key) DO UPDATE SET
            home_score    = COALESCE(excluded.home_score, results.home_score),
            away_score    = COALESCE(excluded.away_score, results.away_score),
            ht_home_score = COALESCE(excluded.ht_home_score, results.ht_home_score),
            ht_away_score = COALESCE(excluded.ht_away_score, results.ht_away_score),
            winner        = COALESCE(excluded.winner, results.winner),
            selections    = excluded.selections,
            run_id        = excluded.run_id,
            captured_at   = excluded.captured_at,
            updated_at    = excluded.updated_at
        """,
        (
            result_key,
            league_id,
            result["home_team"],
            result["away_team"],
            result["result_time"],
            start_time,
            result.get("home_score"),
            result.get("away_score"),
            result.get("ht_home_score"),
            result.get("ht_away_score"),
            result.get("winner"),
            json.dumps(
                result.get("selections") or [],
                ensure_ascii=False,
            ),
            run_id,
            captured_at,
            now_iso(),
        ),
    )


# Jogos criados a partir do resultado (o feed de
# resultados não traz fixture_id) usam este prefixo.
SYNTHETIC_FIXTURE_PREFIX = "res:"


def match_results(
    conn,
):
    """
    Liga cada resultado a um jogo e aplica o placar.

    1. Jogo real (do coupon) com a mesma liga, os
       mesmos times e o mesmo start_time exato (o
       confronto se repete em outros horários).
    2. Sem jogo real, cria o jogo a partir do próprio
       resultado, com fixture_id sintético
       ("res:" + result_key). Se o coupon real chegar
       depois, o resultado passa para ele e o jogo
       sintético é apagado.
    3. Aplica o placar via set_score() onde ele ainda
       não está.

    Resultados sem start_time (sem referência de data)
    ficam só na tabela results. Retorna quantos
    placares aplicou.
    """

    real_game = """
        SELECT g.fixture_id
        FROM games g
        WHERE g.league_id = results.league_id
          AND g.home_team = results.home_team
          AND g.away_team = results.away_team
          AND g.start_time = results.start_time
          AND g.fixture_id NOT LIKE 'res:%'
    """

    # Sintético -> real, quando o coupon apareceu.
    replaced = conn.execute(
        f"""
        SELECT result_key, fixture_id AS synthetic, ({real_game}) AS real
        FROM results
        WHERE fixture_id LIKE 'res:%'
          AND ({real_game}) IS NOT NULL
        """
    ).fetchall()

    for row in replaced:

        conn.execute(
            "UPDATE results SET fixture_id = ? WHERE result_key = ?",
            (
                row["real"],
                row["result_key"],
            ),
        )

        conn.execute(
            "DELETE FROM games WHERE fixture_id = ?",
            (
                row["synthetic"],
            ),
        )

    conn.execute(
        f"""
        UPDATE results
        SET fixture_id = ({real_game})
        WHERE fixture_id IS NULL
          AND start_time IS NOT NULL
        """
    )

    orphans = conn.execute(
        """
        SELECT *
        FROM results
        WHERE fixture_id IS NULL
          AND start_time IS NOT NULL
        """
    ).fetchall()

    for row in orphans:

        fixture_id = (
            SYNTHETIC_FIXTURE_PREFIX
            + row["result_key"]
        )

        # games.league_id é FK: garante a liga
        # (o nome, se já existir, é mantido).
        upsert_league(
            conn,
            row["league_id"],
            None,
        )

        conn.execute(
            """
            INSERT OR IGNORE INTO games (
                fixture_id, league_id,
                home_team, away_team, start_time,
                run_id, captured_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fixture_id,
                row["league_id"],
                row["home_team"],
                row["away_team"],
                row["start_time"],
                row["run_id"],
                row["captured_at"],
                now_iso(),
            ),
        )

        conn.execute(
            "UPDATE results SET fixture_id = ? WHERE result_key = ?",
            (
                fixture_id,
                row["result_key"],
            ),
        )

    pending = conn.execute(
        """
        SELECT r.fixture_id, r.home_score, r.away_score
        FROM results r
        JOIN games g
            ON g.fixture_id = r.fixture_id
        WHERE r.home_score IS NOT NULL
          AND (
              g.home_score IS NOT r.home_score
              OR g.away_score IS NOT r.away_score
          )
        """
    ).fetchall()

    for row in pending:
        set_score(
            conn,
            row["fixture_id"],
            row["home_score"],
            row["away_score"],
        )

    return len(
        pending
    )
