"""
Consultas de leitura usadas pelo dashboard (dashboard.py).

Funções puras: recebem uma conexão SQLite e devolvem listas de
dicts, sem depender do Streamlit, para poderem ser testadas.
"""

import sqlite3

from pathlib import Path


def rows_to_dicts(
    rows,
):
    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# CONEXÃO
# ============================================================

def connect_readonly(
    path,
):
    # Não usa database.connect(): aquele aplica o DDL (escrita).
    conn = sqlite3.connect(
        # as_uri() escapa espaços, "?", "#" e "%" do caminho.
        Path(path).resolve().as_uri() + "?mode=ro",
        uri=True,
    )

    conn.row_factory = sqlite3.Row

    return conn


# ============================================================
# LIGAS
# ============================================================

def list_leagues(
    conn,
):
    # O mesmo nome aparece com vários league_id: filtra por nome.
    rows = conn.execute(
        """
        SELECT DISTINCT name
        FROM leagues
        WHERE name IS NOT NULL
        ORDER BY name
        """
    )

    return [
        row[0]
        for row in rows
    ]


# ============================================================
# JOGOS
# ============================================================

def list_games(
    conn,
    leagues: list[str] | None = None,
):
    """
    Histórico de jogos, do mais recente para o mais antigo.
    leagues vazio ou None = todas as ligas.
    """

    sql = """
        SELECT
            fixture_id,
            data,
            hora,
            liga,
            confronto,
            placar,
            start_time
        FROM games_view
    """

    params = []

    if leagues:
        placeholders = ", ".join(
            "?" for _ in leagues
        )

        sql += f" WHERE liga IN ({placeholders})"

        params = list(leagues)

    sql += " ORDER BY start_time DESC, fixture_id"

    return rows_to_dicts(
        conn.execute(
            sql,
            params,
        )
    )


def get_game(
    conn,
    fixture_id: str,
):
    row = conn.execute(
        """
        SELECT
            g.fixture_id,
            g.meeting_id,
            g.home_team,
            g.away_team,
            g.start_time,
            g.home_score,
            g.away_score,
            g.league_id,
            l.name AS liga,
            g.run_id,
            g.captured_at,
            g.updated_at
        FROM games g
        LEFT JOIN leagues l
            ON l.league_id = g.league_id
        WHERE g.fixture_id = ?
        """,
        (
            fixture_id,
        ),
    ).fetchone()

    return dict(row) if row else None


# ============================================================
# ODDS
# ============================================================

def get_odds(
    conn,
    fixture_id: str,
):
    # Ordem do coupon: posição do mercado, depois da seleção.
    return rows_to_dicts(
        conn.execute(
            """
            SELECT
                m.group_name,
                m.market_name,
                s.name AS selection,
                s.label,
                s.handicap,
                s.odds_decimal,
                s.odds_fractional,
                s.suspended
            FROM selections s
            JOIN markets m
                ON m.id = s.market_pk
            WHERE m.fixture_id = ?
            ORDER BY
                m.position,
                s.position
            """,
            (
                fixture_id,
            ),
        )
    )
