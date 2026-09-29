import argparse
import asyncio
import json

from datetime import datetime

from camoufox.async_api import AsyncCamoufox

from config import BASE_URL, RAW_DIR
from utils import now_iso
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
# MAIN
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Coleta todos os jogos de todas as "
            "ligas de Futebol Virtual."
        ),
    )

    parser.add_argument(
        "--no-results",
        action="store_true",
        help="Não clica na aba Resultados de cada liga.",
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

        "leagues":
            [],
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
        # LIGAS
        # ====================================================

        cards = await get_league_cards(
            page
        )

        print_league_cards(
            cards
        )

        positions = list(
            range(
                1,
                len(cards) + 1,
            )
        )

        run_metadata["available_leagues"] = [
            card["name"]
            for card in cards
        ]

        if not positions:
            return

        # ====================================================
        # COLETA
        # ====================================================

        for position in positions:

            # Reconsulta os cards: a interface
            # rerenderiza ao trocar de liga.
            cards = await get_league_cards(
                page
            )

            league = {
                "position": position,
                "name": None,
                "league_id": None,
                "time_slots": [],
            }

            run_metadata["leagues"].append(
                league
            )

            if position > len(cards):

                league["error"] = "card not found"

                continue

            card = cards[position - 1]

            league["name"] = card["name"]

            print(
                "\n"
                + "=" * 100
            )

            print(
                f"COLETA DOS HORÁRIOS [{position}/{len(cards)}]:",
                card["name"],
            )

            print(
                "=" * 100
            )

            if not await activate_league_card(
                page,
                card,
            ):
                league["error"] = "select failed"

                continue

            # Resultados antes dos horários: a aba
            # mostra só 2 jogos por vez e a janela
            # é curta; os jogos futuros continuam
            # na faixa por vários minutos.
            if not args.no_results:
                league["results"] = await collect_results(
                    page=page,
                    collector=collector,
                )

            league["time_slots"] = await collect_time_slots(
                page=page,
                collector=collector,
            )

        # Dá tempo aos handlers de response
        # terminarem de gravar os arquivos.
        await page.wait_for_timeout(
            2000
        )

    run_metadata["coupons"] = collector.coupons

    print(
        "\n"
        + "=" * 100
    )

    print(
        "RESUMO"
    )

    for league in run_metadata["leagues"]:

        slots = league["time_slots"]

        attach_coupon_files(
            slots,
            collector.coupons,
        )

        # ID real da liga (campo C do PD),
        # pois há ligas com o mesmo nome.
        league["league_id"] = next(
            (
                slot["league_id"]
                for slot in slots
                if slot["league_id"]
            ),
            None,
        )

        filled = sum(
            1
            for slot in slots
            if slot.get("file")
            and not slot.get("empty")
        )

        print(
            f"\n[{league['position']}] {league['name']} "
            f"(C={league['league_id']}) "
            f"jogos com dados: {filled}/{len(slots)}"
            + (
                f" erro={league['error']}"
                if league.get("error")
                else ""
            )
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

    # Coupons sem horário correspondente
    # (em geral, os de transição: stale=true),
    # que podem duplicar jogos de outra liga.
    linked_files = {
        slot["file"]
        for league in run_metadata["leagues"]
        for slot in league["time_slots"]
        if slot.get("file")
    }

    for coupon in collector.coupons:
        coupon["linked"] = (
            coupon["file"]
            in linked_files
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
