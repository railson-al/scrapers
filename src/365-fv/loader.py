"""
Estágio 4: normalized -> SQLite.

Lê data/normalized/<run_id>/*_coupon.json e grava games,
markets e selections no banco (DB_PATH). A liga vem do
run.json da captura crua, casada pelo nome do arquivo.

Idempotente: rodar de novo a mesma run só atualiza os jogos
e troca as odds pelo snapshot mais recente.
"""

import argparse

from pathlib import Path

from config import RAW_DIR, NORMALIZED_DIR, DB_PATH
from database import (
    connect,
    upsert_league,
    upsert_game,
    replace_markets,
)
from utils import (
    load_json,
    find_latest_run,
    parse_pd,
)


# ============================================================
# LIGAS
# ============================================================

def build_league_map(
    run_id: str,
):
    """
    {"0003_coupon.json": ("20940364", "Express Cup ...")}
    a partir de data/raw/<run_id>/run.json.
    """

    run_file = (
        RAW_DIR
        / run_id
        / "run.json"
    )

    if not run_file.exists():

        print(
            "Aviso: run.json não encontrado:",
            run_file,
        )

        return {}

    run = load_json(
        run_file
    )

    league_map = {}

    for league in run.get("leagues") or []:

        for slot in league.get("time_slots") or []:

            file_name = slot.get("file")

            if not file_name:
                continue

            league_map[file_name] = (
                slot.get("league_id")
                or league.get("league_id"),
                league.get("name"),
            )

    return league_map


def league_from_pd(
    pd: str | None,
):
    # Fallback: o código M do pd do coupon é o id da liga.
    value = parse_pd(pd).get("M")

    if isinstance(value, list):
        value = value[0]

    return value or None


# ============================================================
# LOAD
# ============================================================

def load_file(
    conn,
    input_file: Path,
    league_map: dict,
):
    data = load_json(
        input_file
    )

    run_id = input_file.parent.name

    source = data.get("source") or {}

    captured_at = source.get("captured_at") or ""

    league_id, league_name = league_map.get(
        input_file.name,
        (None, None),
    )

    if league_id is None:
        league_id = league_from_pd(
            source.get("pd")
        )

    game_count = 0
    market_count = 0
    selection_count = 0

    with conn:

        if league_id:
            upsert_league(
                conn,
                league_id,
                league_name,
            )

        for event in data.get("events") or []:

            if not event.get("fixture_id"):
                continue

            upsert_game(
                conn,
                event,
                league_id=league_id,
                run_id=run_id,
                captured_at=captured_at,
            )

            markets, selections = replace_markets(
                conn,
                event["fixture_id"],
                event.get("markets") or [],
            )

            game_count += 1
            market_count += markets
            selection_count += selections

    print(
        f"{input_file.name}: "
        f"{game_count} jogos | "
        f"{market_count} mercados | "
        f"{selection_count} seleções | "
        f"liga: {league_name or league_id}"
    )

    return game_count


def load_run(
    conn,
    run_dir: Path,
):
    run_id = run_dir.name

    coupon_files = sorted(
        run_dir.glob(
            "*_coupon.json"
        )
    )

    if not coupon_files:

        print(
            "Nenhum coupon encontrado em:"
        )

        print(
            run_dir
        )

        return

    print(
        "\nRun:",
        run_id,
    )

    print(
        "Coupons:",
        len(
            coupon_files
        ),
    )

    league_map = build_league_map(
        run_id
    )

    total = 0

    for input_file in coupon_files:

        total += load_file(
            conn,
            input_file,
            league_map,
        )

    print(
        "\n"
        + "=" * 80
    )

    print(
        "CARGA FINALIZADA"
    )

    print(
        "=" * 80
    )

    print(
        "Jogos gravados:",
        total,
    )

    print(
        "Database:",
        DB_PATH,
    )


# ============================================================
# CLI
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Loader SQLite "
            "Bet365 Virtual Sports"
        )
    )

    parser.add_argument(
        "--run",
        type=str,
    )

    parser.add_argument(
        "--file",
        type=str,
    )

    args = parser.parse_args()

    conn = connect()

    try:

        # ====================================================
        # FILE
        # ====================================================

        if args.file:

            input_file = Path(
                args.file
            )

            if not input_file.exists():

                print(
                    "Arquivo não encontrado:"
                )

                print(
                    input_file
                )

                return

            load_file(
                conn,
                input_file,
                build_league_map(
                    input_file.parent.name
                ),
            )

            return

        # ====================================================
        # RUN
        # ====================================================

        if args.run:

            run_dir = Path(
                args.run
            )

            if not run_dir.exists():

                run_dir = (
                    NORMALIZED_DIR
                    / args.run
                )

            if not run_dir.exists():

                print(
                    "Run não encontrada:"
                )

                print(
                    args.run
                )

                return

        else:

            run_dir = find_latest_run(NORMALIZED_DIR)

            if run_dir is None:

                print(
                    "Nenhuma run encontrada em:"
                )

                print(
                    NORMALIZED_DIR
                )

                return

            print(
                "Usando última run:"
            )

            print(
                run_dir
            )

        load_run(
            conn,
            run_dir,
        )

    finally:
        conn.close()


# ============================================================
# ENTRYPOINT
# ============================================================

if __name__ == "__main__":
    main()
