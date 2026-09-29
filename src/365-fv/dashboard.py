"""
Dashboard Streamlit do histórico de jogos (SQLite).

Grid com os jogos filtrados por liga; ao selecionar uma linha
mostra os detalhes do jogo e as odds agrupadas por mercado.

Uso (da raiz do repositório, depois do loader.py):
    uv run streamlit run src/365-fv/dashboard.py
"""

import pandas as pd
import streamlit as st

from config import DB_PATH
from dashboard_queries import (
    connect_readonly,
    list_leagues,
    list_games,
    get_game,
    get_odds,
)


GRID_COLUMNS = [
    "data",
    "hora",
    "liga",
    "confronto",
    "placar",
]


# ============================================================
# DETALHES
# ============================================================

def format_score(
    game: dict,
):
    if game["home_score"] is None:
        return "—"

    return f"{game['home_score']} - {game['away_score']}"


def render_details(
    conn,
    fixture_id: str,
):
    game = get_game(
        conn,
        fixture_id,
    )

    if game is None:
        st.warning(
            f"Jogo {fixture_id} não encontrado."
        )
        return

    st.subheader(
        f"{game['home_team']} x {game['away_team']}"
    )

    col_league, col_start, col_score = st.columns(3)

    col_league.metric("Liga", game["liga"] or game["league_id"] or "—")
    col_start.metric("Início", game["start_time"].replace("T", " "))
    col_score.metric("Placar", format_score(game))

    st.caption(
        f"fixture_id {game['fixture_id']} · "
        f"meeting_id {game['meeting_id'] or '—'} · "
        f"run {game['run_id']} · "
        f"capturado em {game['captured_at']}"
    )

    odds = get_odds(
        conn,
        fixture_id,
    )

    if not odds:
        st.info(
            "Sem odds gravadas para este jogo."
        )
        return

    df = pd.DataFrame(odds)

    df["suspended"] = df["suspended"].fillna(0).astype(bool)

    # groupby(sort=False) mantém a ordem do coupon.
    for group_name, group in df.groupby(
        df["group_name"].fillna("(sem grupo)"),
        sort=False,
    ):
        with st.expander(
            group_name,
            expanded=False,
        ):
            st.dataframe(
                group.drop(columns=["group_name"]),
                hide_index=True,
                width="stretch",
                column_config={
                    "market_name": "Mercado",
                    "selection": "Seleção",
                    "label": "Rótulo",
                    "handicap": "Handicap",
                    "odds_decimal": st.column_config.NumberColumn(
                        "Odd",
                        format="%.2f",
                    ),
                    "odds_fractional": "Fracionária",
                    "suspended": "Suspensa",
                },
            )


# ============================================================
# APP
# ============================================================

def main():

    st.set_page_config(
        page_title="Bet365 Virtual Football",
        layout="wide",
    )

    st.title(
        "Histórico de jogos"
    )

    if not DB_PATH.exists():
        st.error(
            f"Banco não encontrado em {DB_PATH}. "
            "Rode o loader.py a partir da raiz do repositório."
        )
        st.stop()

    conn = connect_readonly(
        DB_PATH
    )

    try:

        leagues = st.sidebar.multiselect(
            "Liga",
            list_leagues(conn),
            placeholder="Todas as ligas",
        )

        games = list_games(
            conn,
            leagues=leagues,
        )

        st.caption(
            f"{len(games)} jogos · "
            "selecione uma linha para ver os detalhes"
        )

        if not games:
            st.info(
                "Nenhum jogo para o filtro atual."
            )
            return

        df = pd.DataFrame(games)

        df["placar"] = df["placar"].fillna("—")

        event = st.dataframe(
            df,
            column_order=GRID_COLUMNS,
            column_config={
                "data": "Data",
                "hora": "Hora",
                "liga": "Liga",
                "confronto": "Confronto",
                "placar": "Placar",
            },
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            # Trocar o filtro (ou o loader gravar jogos novos) zera a
            # seleção: os índices de linha mudam.
            key=f"games_grid_{'|'.join(leagues)}_{len(df)}_{df['fixture_id'].iloc[0]}",
        )

        rows = event.selection.rows

        if rows and rows[0] < len(df):

            st.divider()

            render_details(
                conn,
                df.iloc[rows[0]]["fixture_id"],
            )

    finally:
        conn.close()


main()
