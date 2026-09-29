"""
Camada de database (SQLite em dev) compartilhada pelos scripts.

O schema fica em schema.sql, ao lado deste arquivo, e é aplicado
a cada conexão (é idempotente).
"""

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
