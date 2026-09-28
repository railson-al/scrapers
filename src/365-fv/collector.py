import argparse
import asyncio
import json

from datetime import datetime

from camoufox.async_api import AsyncCamoufox

from config import BASE_URL, RAW_DIR
from utils import now_iso, normalize_text
from navigation import (
    RawCollector,
    find_virtual_sports_entry,
    find_football_click_candidates,
    click_football_and_wait,
    get_league_cards,
    print_league_cards,
    activate_league_card,
    collect_time_slots,
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
# MAIN
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

    return parser.parse_args()


async def main():

    args = parse_args()

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
        "\nRUN:"
    )

    print(
        run_id
    )

    print(
        "\nOutput:"
    )

    print(
        run_dir
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
    }

    run_file = (
        run_dir
        / "run.json"
    )

    run_file.write_text(
        json.dumps(
            run_metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    collector = RawCollector(
        output_dir=run_dir,
    )

    async with AsyncCamoufox(
        headless=False,
    ) as browser:

        page = (
            await browser.new_page()
        )

        page.on(
            "request",
            collector.log_request,
        )

        page.on(
            "response",
            collector.capture_response,
        )

        # ====================================================
        # HOME
        # ====================================================

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

        # ====================================================
        # ENCONTRA ESPORTES VIRTUAIS
        # ====================================================

        virtual_sports = (
            await find_virtual_sports_entry(
                page=page,
                timeout_seconds=30,
            )
        )

        if virtual_sports is None:

            print(
                "\nERRO:"
                " Esportes Virtuais "
                "não encontrado."
            )

            return

        print(
            "\n'Esportes Virtuais' "
            "encontrado."
        )

        try:

            html = (
                await virtual_sports.evaluate(
                    "(el) => el.outerHTML"
                )
            )

            print(
                "Elemento:"
            )

            print(
                html
            )

        except Exception:
            pass

        # ====================================================
        # B144
        # ====================================================

        print(
            "\nEntrando em "
            "Esportes Virtuais..."
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

            splash_response = (
                await splash_info.value
            )

        except Exception as exc:

            print(
                "\nERRO esperando B144:"
            )

            print(
                exc
            )

            return

        print(
            "\nVirtual Sports carregado."
        )

        print(
            "Status:",
            splash_response.status,
        )

        # ====================================================
        # FUTEBOL
        # ====================================================

        candidates = (
            await find_football_click_candidates(
                page=page,
                timeout_seconds=30,
            )
        )

        if not candidates:

            print(
                "\nNenhum candidato "
                "de Futebol encontrado."
            )

            return

        (
            football_splash,
            first_coupon,
        ) = (
            await click_football_and_wait(
                page=page,
                candidates=candidates,
            )
        )

        if football_splash is None:

            print(
                "\nNenhum candidato "
                "disparou B146."
            )

            return

        # ====================================================
        # LIGA
        # ====================================================

        position, cards = await select_league(
            page=page,
            wanted=args.league,
        )

        run_metadata["available_leagues"] = [
            card["name"]
            for card in cards
        ]

        if position is None:
            return

        card = cards[position - 1]

        league_name = card["name"]

        run_metadata["league"] = league_name

        run_metadata["league_position"] = position

        if not await activate_league_card(
            page,
            card,
        ):
            return

        # ====================================================
        # COLETA
        # ====================================================

        print(
            "\n"
            + "=" * 100
        )

        print(
            "COLETA DOS HORÁRIOS:",
            league_name,
        )

        print(
            "=" * 100
        )

        slots = await collect_time_slots(
            page=page,
            collector=collector,
        )

        # Dá tempo aos handlers de response
        # terminarem de gravar os arquivos.
        await page.wait_for_timeout(
            2000
        )

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
        None,
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
        league_name,
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

    run_metadata[
        "finished_at"
    ] = now_iso()

    run_file.write_text(
        json.dumps(
            run_metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
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
