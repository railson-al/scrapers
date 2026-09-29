"""
Coleta os jogos (horários) e os resultados de uma liga de Futebol
Virtual. Com --watch, mantém a página aberta e repete a coleta a
cada N segundos, processando cada run até o SQLite.
"""

import argparse
import asyncio
import contextlib
import io
import json
import re
import traceback

from datetime import datetime

from camoufox.async_api import AsyncCamoufox

import loader as load_stage
import normalizer as normalize_stage
import parser as parse_stage

from config import BASE_URL, RAW_DIR, PARSED_DIR, NORMALIZED_DIR
from database import connect
from utils import now_iso, normalize_text, load_json
from navigation import (
    RawCollector,
    find_virtual_sports_entry,
    find_football_click_candidates,
    click_football_and_wait,
    get_league_cards,
    print_league_cards,
    activate_league_card,
    collect_time_slots,
    collect_results,
    attach_coupon_files,
)


# ============================================================
# LIGAS
# ============================================================

def match_league(
    cards,
    wanted: str,
):
    """
    Casa o valor de --league com os cards.
    Um número seleciona pela posição da
    lista impressa (existem ligas com o
    mesmo nome). Senão: igualdade exata tem
    prioridade, depois trecho do nome (sem
    diferenciar maiúsculas).
    Retorna a lista de matches.
    """

    wanted = normalize_text(
        wanted
    )

    if wanted.isdigit():

        position = int(wanted)

        if 1 <= position <= len(cards):
            return [
                cards[position - 1]
            ]

        return []

    wanted = wanted.lower()

    exact = [
        card
        for card in cards
        if card["name"].lower() == wanted
    ]

    if exact:
        return exact

    return [
        card
        for card in cards
        if wanted in card["name"].lower()
    ]


async def select_league(
    page,
    wanted: str | None,
):
    """
    Seleciona a liga pedida.
    Sem --league, mantém a liga ativa.
    Retorna (posição 1-based, cards) ou
    (None, cards) em caso de erro.
    """

    cards = await get_league_cards(
        page
    )

    print_league_cards(
        cards
    )

    if not cards:
        print(
            "\nERRO: nenhum card de liga "
            "encontrado."
        )

        return None, cards

    if wanted is None:

        active = [
            card
            for card in cards
            if card["active"]
        ]

        if not active:
            print(
                "\nERRO: liga ativa "
                "não identificada."
            )

            return None, cards

        return cards.index(active[0]) + 1, cards

    matches = match_league(
        cards,
        wanted,
    )

    if len(matches) != 1:

        print(
            f"\nERRO: --league '{wanted}' "
            f"casou com {len(matches)} ligas. "
            "Use o número [N] da lista acima "
            "ou um trecho que identifique "
            "apenas uma liga."
        )

        return None, cards

    return cards.index(matches[0]) + 1, cards


# ============================================================
# ARGUMENTOS
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Coleta todos os jogos (horários) "
            "de uma liga de Futebol Virtual. "
            "Para todas as ligas, use collector_all.py."
        ),
    )

    parser.add_argument(
        "--league",
        help=(
            "Nome ou trecho do nome da liga "
            "(ex.: 'Premier', 'Euro Cup'). "
            "Padrão: liga ativa ao abrir Futebol."
        ),
    )

    parser.add_argument(
        "--no-results",
        action="store_true",
        help="Não clica na aba Resultados.",
    )

    parser.add_argument(
        "--watch",
        type=int,
        metavar="SEGUNDOS",
        help=(
            "Mantém o navegador aberto e repete a "
            "coleta (Resultados + horários) a cada "
            "SEGUNDOS, sem recarregar a página. Cada "
            "ciclo é uma run nova, já processada por "
            "parser -> normalizer -> loader."
        ),
    )

    parser.add_argument(
        "--click-delay",
        type=int,
        default=1000,
        metavar="MS",
        help=(
            "Espera entre os cliques nos horários, "
            "depois do coupon chegar (padrão: 1000)."
        ),
    )

    parser.add_argument(
        "--cycles",
        type=int,
        default=0,
        help="Com --watch: para após N ciclos (0 = sem limite).",
    )

    return parser.parse_args()


# ============================================================
# RUN
# ============================================================

# Falhas seguidas (sem coupon algum) antes de
# encerrar o --watch; cada falha renavega.
MAX_WATCH_FAILURES = 3


def new_run(
    args,
    league: dict | None = None,
):
    """
    Cria data/raw/<run_id>/ e o run.json inicial.
    league: liga já selecionada (--watch), para
    os ciclos seguintes não perderem o nome.
    """

    run_id = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    run_dir = (
        RAW_DIR
        / run_id
    )

    run_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "\nRUN:",
        run_id,
    )

    print(
        "Output:",
        run_dir,
    )

    run_metadata = {
        "run_id":
            run_id,
        "started_at":
            now_iso(),
        "base_url":
            BASE_URL,
        "collector":
            "bet365-virtual-sports",
        "target":
            "football",
        "league_requested":
            args.league,
        "click_delay_ms":
            args.click_delay,
        **(league or {}),
    }

    write_run_file(
        run_dir,
        run_metadata,
    )

    return (
        run_dir,
        run_metadata,
    )


def write_run_file(
    run_dir,
    run_metadata,
):
    (run_dir / "run.json").write_text(
        json.dumps(
            run_metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def attach_collector(
    page,
    collector,
):
    page.on(
        "request",
        collector.log_request,
    )

    page.on(
        "response",
        collector.capture_response,
    )


def detach_collector(
    page,
    collector,
):
    page.remove_listener(
        "request",
        collector.log_request,
    )

    page.remove_listener(
        "response",
        collector.capture_response,
    )


# ============================================================
# NAVEGAÇÃO ATÉ A LIGA
# ============================================================

async def open_league(
    page,
    args,
    run_metadata,
):
    """
    Home -> Esportes Virtuais (B144) -> Futebol
    (B146) -> liga pedida. Preenche a liga em
    run_metadata e retorna True em caso de sucesso.
    """

    print(
        "\nAbrindo Bet365..."
    )

    await page.goto(
        BASE_URL,
        wait_until="domcontentloaded",
    )

    print(
        "Página inicial carregada."
    )

    await page.wait_for_timeout(
        3000
    )

    # ========================================================
    # ESPORTES VIRTUAIS (B144)
    # ========================================================

    virtual_sports = await find_virtual_sports_entry(
        page=page,
        timeout_seconds=30,
    )

    if virtual_sports is None:

        print(
            "\nERRO: Esportes Virtuais não encontrado."
        )

        return False

    print(
        "\nEntrando em Esportes Virtuais..."
    )

    try:
        async with page.expect_response(
            lambda response:
                (
                    "/virtualsportscontentapi/splash"
                    in response.url.lower()
                    and
                    "%23avr%23b144%23"
                    in response.url.lower()
                ),
            timeout=30_000,
        ) as splash_info:
            await virtual_sports.click()

        splash_response = await splash_info.value

    except Exception as exc:

        print(
            "\nERRO esperando B144:",
            exc,
        )

        return False

    print(
        "\nVirtual Sports carregado. Status:",
        splash_response.status,
    )

    # ========================================================
    # FUTEBOL (B146)
    # ========================================================

    candidates = await find_football_click_candidates(
        page=page,
        timeout_seconds=30,
    )

    if not candidates:

        print(
            "\nERRO: nenhum candidato de Futebol encontrado."
        )

        return False

    football_splash, _ = await click_football_and_wait(
        page=page,
        candidates=candidates,
    )

    if football_splash is None:

        print(
            "\nERRO: nenhum candidato disparou B146."
        )

        return False

    # ========================================================
    # LIGA
    # ========================================================

    position, cards = await select_league(
        page=page,
        wanted=args.league,
    )

    run_metadata["available_leagues"] = [
        card["name"]
        for card in cards
    ]

    if position is None:
        return False

    card = cards[position - 1]

    run_metadata["league"] = card["name"]
    run_metadata["league_position"] = position

    return await activate_league_card(
        page,
        card,
    )


# ============================================================
# COLETA DE UM CICLO
# ============================================================

async def collect_league(
    page,
    collector,
    args,
    run_metadata,
):
    print(
        "\n"
        + "=" * 100
    )

    print(
        "COLETA:",
        run_metadata.get("league"),
    )

    print(
        "=" * 100
    )

    # Resultados antes dos horários: a aba
    # mostra só 2 jogos por vez e a janela
    # é curta; os jogos futuros continuam
    # na faixa por vários minutos.
    if not args.no_results:
        run_metadata["results"] = await collect_results(
            page=page,
            collector=collector,
        )

    slots = await collect_time_slots(
        page=page,
        collector=collector,
        click_delay_ms=args.click_delay,
    )

    # Dá tempo aos handlers de response
    # terminarem de gravar os arquivos.
    await page.wait_for_timeout(
        2000
    )

    return slots


def finish_run(
    run_dir,
    run_metadata,
    slots,
    collector,
):
    attach_coupon_files(
        slots,
        collector.coupons,
    )

    # ID real da liga (campo C do PD),
    # pois há ligas com o mesmo nome.
    run_metadata["league_id"] = next(
        (
            slot["league_id"]
            for slot in slots
            if slot["league_id"]
        ),
        run_metadata.get("league_id"),
    )

    run_metadata["time_slots"] = slots

    # Coupons sem horário correspondente
    # (em geral, os de transição: stale=true),
    # que podem duplicar jogos de outra liga.
    linked_files = {
        slot["file"]
        for slot in slots
        if slot.get("file")
    }

    for coupon in collector.coupons:
        coupon["linked"] = (
            coupon["file"]
            in linked_files
        )

    run_metadata["coupons"] = collector.coupons

    print(
        "\n"
        + "=" * 100
    )

    print(
        "RESUMO:",
        run_metadata.get("league"),
        f"(C={run_metadata['league_id']})",
    )

    for slot in slots:
        print(
            f"  {slot['time']} "
            f"E={slot['challenge_id']} "
            f"file={slot.get('file')} "
            f"size={slot.get('body_size')} "
            f"empty={slot.get('empty')}"
            + (
                " HORÁRIO DIVERGENTE"
                if slot.get("start_matches") is False
                else ""
            )
            + (
                f" erro={slot['error']}"
                if slot.get("error")
                else ""
            )
        )

    unlinked = [
        coupon["file"]
        for coupon in collector.coupons
        if not coupon["linked"]
    ]

    if unlinked:
        print(
            f"\nCoupons sem horário "
            f"(linked=false): {len(unlinked)}",
            unlinked,
        )

    run_metadata["finished_at"] = now_iso()

    write_run_file(
        run_dir,
        run_metadata,
    )


# ============================================================
# PIPELINE (--watch)
# ============================================================

def process_run(
    run_dir,
    league_id: str | None,
):
    """
    parser -> normalizer -> loader na run recém
    fechada, no mesmo processo. A saída detalhada
    dos estágios é suprimida; imprime um resumo.
    Uma falha aqui não interrompe o --watch.
    """

    run_id = run_dir.name

    output = io.StringIO()

    try:

        with contextlib.redirect_stdout(output):

            parse_stage.parse_run(
                run_dir
            )

            normalize_stage.normalize_run(
                PARSED_DIR / run_id
            )

            conn = connect()

            try:
                load_stage.load_run(
                    conn,
                    NORMALIZED_DIR / run_id,
                )

            finally:
                conn.close()

    except Exception:

        print(
            "\nERRO no pipeline da run",
            run_id,
        )

        traceback.print_exc()

        return

    applied = re.findall(
        r"Placares aplicados: (\d+)",
        output.getvalue(),
    )

    shown = []

    for results_file in sorted(
        (NORMALIZED_DIR / run_id).glob(
            "*_results.json"
        )
    ):
        shown += [
            result["result_time"] or "?"
            for result in load_json(
                results_file
            ).get("results") or []
        ]

    conn = connect()

    try:
        counts = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM games WHERE league_id = :league),
                (SELECT COUNT(*) FROM results WHERE league_id = :league),
                (SELECT COUNT(home_score) FROM games WHERE league_id = :league)
            """,
            {
                "league": league_id,
            },
        ).fetchone()

    finally:
        conn.close()

    print(
        f"\n[pipeline] run={run_id} "
        f"aba Resultados={','.join(shown) or '-'} "
        f"placares aplicados={applied[-1] if applied else 0} "
        f"| liga {league_id}: jogos={counts[0]} "
        f"resultados={counts[1]} com placar={counts[2]}"
    )


# ============================================================
# MAIN
# ============================================================

async def watch(
    page,
    args,
    collector,
    run_dir,
    run_metadata,
):
    """
    Repete a coleta na mesma página a cada
    args.watch segundos. Cada ciclo fecha a
    própria run. Ciclo sem coupon algum conta
    como falha e renavega a partir da home.
    """

    loop = asyncio.get_running_loop()

    cycle = 1

    failures = 0

    # Liga fixa entre ciclos; league_id só
    # é conhecido depois do 1º ciclo.
    league_keys = (
        "league",
        "league_position",
        "available_leagues",
    )

    while True:

        started = loop.time()

        print(
            f"\n[watch] ciclo {cycle}"
            + (f"/{args.cycles}" if args.cycles else "")
        )

        slots = []

        try:
            slots = await collect_league(
                page,
                collector,
                args,
                run_metadata,
            )

        except Exception as exc:

            print(
                "\nERRO no ciclo:",
                exc,
            )

        finish_run(
            run_dir,
            run_metadata,
            slots,
            collector,
        )

        filled = sum(
            1
            for slot in slots
            if slot.get("file")
            and not slot.get("empty")
        )

        print(
            f"\n[watch] ciclo {cycle}: horários com dados "
            f"{filled}/{len(slots)} "
            f"(clique a cada {args.click_delay} ms)"
        )

        process_run(
            run_dir,
            run_metadata.get("league_id"),
        )

        if any(
            slot.get("file")
            for slot in slots
        ):
            failures = 0

        else:
            failures += 1

            print(
                f"\n[watch] ciclo sem coupons "
                f"({failures}/{MAX_WATCH_FAILURES})"
            )

        if failures >= MAX_WATCH_FAILURES:

            print(
                "\n[watch] falhas seguidas demais, encerrando."
            )

            return

        if args.cycles and cycle >= args.cycles:

            print(
                "\n[watch] ciclos concluídos."
            )

            return

        wait = args.watch - (
            loop.time() - started
        )

        if page.is_closed():

            print(
                "\n[watch] navegador/página fechado, encerrando."
            )

            return

        if wait > 0:

            try:
                await page.wait_for_timeout(
                    wait * 1000
                )

            except Exception as exc:

                # Ex.: janela fechada durante a espera.
                print(
                    "\n[watch] página indisponível, encerrando:",
                    exc,
                )

                return

        cycle += 1

        # Run nova para o próximo ciclo.
        detach_collector(
            page,
            collector,
        )

        run_dir, run_metadata = new_run(
            args,
            {
                **{
                    key: run_metadata.get(key)
                    for key in league_keys
                },
                "league_id": run_metadata.get(
                    "league_id"
                ),
            },
        )

        collector = RawCollector(
            output_dir=run_dir,
        )

        attach_collector(
            page,
            collector,
        )

        if failures:

            print(
                "\n[watch] renavegando a partir da home..."
            )

            try:
                await open_league(
                    page,
                    args,
                    run_metadata,
                )

            except Exception as exc:

                print(
                    "\nERRO renavegando:",
                    exc,
                )


async def main():

    args = parse_args()

    run_dir, run_metadata = new_run(
        args
    )

    collector = RawCollector(
        output_dir=run_dir,
    )

    async with AsyncCamoufox(
        headless=False,
    ) as browser:

        page = await browser.new_page()

        attach_collector(
            page,
            collector,
        )

        if not await open_league(
            page,
            args,
            run_metadata,
        ):

            run_metadata["finished_at"] = now_iso()

            run_metadata["error"] = "navigation failed"

            write_run_file(
                run_dir,
                run_metadata,
            )

            return

        if args.watch:

            await watch(
                page,
                args,
                collector,
                run_dir,
                run_metadata,
            )

            return

        slots = await collect_league(
            page,
            collector,
            args,
            run_metadata,
        )

    finish_run(
        run_dir,
        run_metadata,
        slots,
        collector,
    )

    print(
        "\nColeta finalizada."
    )


# ============================================================
# ENTRYPOINT
# ============================================================

if __name__ == "__main__":
    asyncio.run(
        main()
    )
