import asyncio
import json
import sys
import time

from datetime import datetime
from pathlib import Path

from camoufox.async_api import AsyncCamoufox

# Permite importar config/utils da pasta pai (src/365-fv).
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent),
)

from config import BASE_URL, DIAGNOSTICS_DIR
from utils import (
    now_iso,
    parse_url_query,
    normalize_text,
    is_interesting_url,
    classify_url,
)


# ============================================================
# NETWORK MONITOR
# ============================================================

class NetworkMonitor:

    def __init__(
        self,
    ):
        self.events = []

        self.started_at = (
            time.monotonic()
        )

    def relative_time(
        self,
    ):
        return round(
            time.monotonic()
            -
            self.started_at,
            3,
        )

    def mark(
        self,
    ):
        return len(
            self.events
        )

    def since(
        self,
        marker,
    ):
        return self.events[
            marker:
        ]

    def on_request(
        self,
        request,
    ):
        if not is_interesting_url(
            request.url
        ):
            return

        query = parse_url_query(
            request.url
        )

        self.events.append(
            {
                "time":
                    self.relative_time(),

                "direction":
                    "request",

                "type":
                    classify_url(
                        request.url
                    ),

                "method":
                    request.method,

                "url":
                    request.url,

                "pd":
                    query.get(
                        "pd"
                    ),
            }
        )

    def on_response(
        self,
        response,
    ):
        if not is_interesting_url(
            response.url
        ):
            return

        query = parse_url_query(
            response.url
        )

        self.events.append(
            {
                "time":
                    self.relative_time(),

                "direction":
                    "response",

                "type":
                    classify_url(
                        response.url
                    ),

                "status":
                    response.status,

                "url":
                    response.url,

                "pd":
                    query.get(
                        "pd"
                    ),
            }
        )


# ============================================================
# ESPORTES VIRTUAIS
# ============================================================

async def find_virtual_sports_entry(
    page,
    timeout_seconds=30,
):
    print(
        "\nProcurando "
        "'Esportes Virtuais'..."
    )

    loop = (
        asyncio.get_running_loop()
    )

    deadline = (
        loop.time()
        + timeout_seconds
    )

    while (
        loop.time()
        < deadline
    ):

        locator = (
            page.get_by_text(
                "Esportes Virtuais",
                exact=True,
            )
        )

        count = (
            await locator.count()
        )

        for index in range(
            count
        ):

            element = (
                locator.nth(
                    index
                )
            )

            try:

                if not (
                    await element.is_visible()
                ):
                    continue

                info = (
                    await element.evaluate(
                        """
                        el => ({
                            tag:
                                el.tagName,

                            className:
                                el.className || "",

                            inNavigation:
                                !!el.closest(
                                    'nav, [role="navigation"]'
                                ),

                            inMain:
                                !!el.closest(
                                    'main, [role="main"]'
                                )
                        })
                        """
                    )
                )

                if (
                    info[
                        "inMain"
                    ]
                    and
                    not info[
                        "inNavigation"
                    ]
                ):

                    print(
                        "Selecionado:",
                        info[
                            "tag"
                        ],
                        info[
                            "className"
                        ],
                    )

                    return element

            except Exception:
                continue

        await page.wait_for_timeout(
            500
        )

    return None


# ============================================================
# FUTEBOL
# ============================================================

async def find_football(
    page,
    timeout_seconds=30,
):
    print(
        "\nProcurando Futebol..."
    )

    loop = (
        asyncio.get_running_loop()
    )

    deadline = (
        loop.time()
        + timeout_seconds
    )

    while (
        loop.time()
        < deadline
    ):

        locator = (
            page.get_by_text(
                "Futebol",
                exact=True,
            )
        )

        count = (
            await locator.count()
        )

        for index in range(
            count
        ):

            element = (
                locator.nth(
                    index
                )
            )

            try:

                if not (
                    await element.is_visible()
                ):
                    continue

                css_class = (
                    await element.get_attribute(
                        "class"
                    )
                    or ""
                )

                if (
                    "vss-d8"
                    in css_class
                ):

                    print(
                        "Futebol encontrado:",
                        css_class,
                    )

                    return element

            except Exception:
                continue

        await page.wait_for_timeout(
            500
        )

    return None


# ============================================================
# MAIN
# ============================================================

async def get_main(
    page,
):
    locator = (
        page.locator(
            '[role="main"]'
        )
    )

    if (
        await locator.count()
    ):

        return locator.first

    return page.locator(
        "body"
    )


# ============================================================
# LEAGUE CARDS
# ============================================================

async def get_league_cards(
    page,
):
    """
    Agora usamos diretamente os cards vcm-d4.

    O texto pode estar distribuído em vários filhos,
    então inner_text() é normalizado.
    """

    main = (
        await get_main(
            page
        )
    )

    cards = (
        main.locator(
            "div.vcm-d4"
        )
    )

    count = (
        await cards.count()
    )

    result = []

    for index in range(
        count
    ):

        card = (
            cards.nth(
                index
            )
        )

        try:

            if not (
                await card.is_visible()
            ):
                continue

            text = normalize_text(
                await card.inner_text()
            )

            if not text:
                continue

            box = (
                await card.bounding_box()
            )

            css_class = (
                await card.get_attribute(
                    "class"
                )
                or ""
            )

            if not box:
                continue

            result.append(
                {
                    "index":
                        index,

                    "name":
                        text,

                    "class":
                        css_class,

                    "x":
                        round(
                            box[
                                "x"
                            ],
                            1,
                        ),

                    "y":
                        round(
                            box[
                                "y"
                            ],
                            1,
                        ),

                    "width":
                        round(
                            box[
                                "width"
                            ],
                            1,
                        ),

                    "height":
                        round(
                            box[
                                "height"
                            ],
                            1,
                        ),

                    "active":
                        "vcm-98c"
                        in css_class.split(),
                }
            )

        except Exception as exc:

            print(
                "Erro lendo card",
                index,
                ":",
                exc,
            )

    return result


# ============================================================
# REENCONTRA CARD
# ============================================================

async def find_league_card_by_name(
    page,
    league_name,
):
    """
    Reconsulta o DOM a cada clique.

    Isso é importante porque ao mudar de liga
    a interface pode rerenderizar os cards.
    """

    main = (
        await get_main(
            page
        )
    )

    cards = (
        main.locator(
            "div.vcm-d4"
        )
    )

    count = (
        await cards.count()
    )

    wanted = normalize_text(
        league_name
    )

    for index in range(
        count
    ):

        card = (
            cards.nth(
                index
            )
        )

        try:

            if not (
                await card.is_visible()
            ):
                continue

            text = normalize_text(
                await card.inner_text()
            )

            if (
                text
                == wanted
            ):

                return card

        except Exception:
            continue

    return None


# ============================================================
# NETWORK
# ============================================================

def print_network_events(
    events,
):
    if not events:

        print(
            "  Nenhum request relevante."
        )

        return

    for event in events:

        direction = (
            ">>>"
            if
            event[
                "direction"
            ]
            == "request"
            else
            "<<<"
        )

        print(
            f"  {direction} "
            f"{event['type'].upper()}"
        )

        if (
            event.get(
                "status"
            )
            is not None
        ):

            print(
                "      status:",
                event[
                    "status"
                ],
            )

        if event.get(
            "pd"
        ):

            print(
                "      PD:",
                event[
                    "pd"
                ],
            )


# ============================================================
# MAIN EXECUTION
# ============================================================

async def main():

    run_id = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    output_dir = (
        DIAGNOSTICS_DIR
        / run_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        output_dir
        / "leagues.json"
    )

    result = {

        "run_id":
            run_id,

        "started_at":
            now_iso(),

        "leagues":
            [],

        "results":
            [],
    }

    print(
        "\n"
        + "=" * 100
    )

    print(
        "TEST LEAGUES V2"
    )

    print(
        "=" * 100
    )

    print(
        "Run:",
        run_id,
    )

    print(
        "Output:",
        output_file,
    )

    monitor = (
        NetworkMonitor()
    )

    async with AsyncCamoufox(
        headless=False,
    ) as browser:

        page = (
            await browser.new_page()
        )

        page.on(
            "request",
            monitor.on_request,
        )

        page.on(
            "response",
            monitor.on_response,
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
        # VIRTUAL SPORTS
        # ====================================================

        virtual_sports = (
            await find_virtual_sports_entry(
                page
            )
        )

        if (
            virtual_sports
            is None
        ):

            print(
                "Esportes Virtuais "
                "não encontrado."
            )

            return

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

            ):

                await virtual_sports.click()

        except Exception as exc:

            print(
                "Erro esperando B144:"
            )

            print(
                exc
            )

            return

        await page.wait_for_timeout(
            1500
        )

        # ====================================================
        # FOOTBALL
        # ====================================================

        football = (
            await find_football(
                page
            )
        )

        if football is None:

            print(
                "Futebol não encontrado."
            )

            return

        print(
            "\nEntrando em Futebol..."
        )

        try:

            async with page.expect_response(

                lambda response:
                    (
                        "/virtualsportscontentapi/splash"
                        in response.url.lower()

                        and

                        "%23avr%23b146"
                        in response.url.lower()
                    ),

                timeout=30_000,

            ):

                await football.click()

        except Exception as exc:

            print(
                "Erro esperando B146:"
            )

            print(
                exc
            )

            return

        # Coupon inicial
        await page.wait_for_timeout(
            3000
        )

        # ====================================================
        # LEAGUES
        # ====================================================

        leagues = (
            await get_league_cards(
                page
            )
        )

        result[
            "leagues"
        ] = leagues

        print(
            "\n"
            + "=" * 100
        )

        print(
            "LIGAS DETECTADAS"
        )

        print(
            "=" * 100
        )

        for index, league in enumerate(
            leagues
        ):

            active_text = (
                " [ATIVA]"
                if league[
                    "active"
                ]
                else ""
            )

            print(
                f"[{index}] "
                f"{league['name']}"
                f"{active_text}"
            )

            print(
                f"    DOM index="
                f"{league['index']}"
            )

            print(
                f"    class="
                f"{league['class']}"
            )

            print(
                f"    x={league['x']} "
                f"y={league['y']}"
            )

        # ====================================================
        # CLICK TEST
        # ====================================================

        print(
            "\n"
            + "=" * 100
        )

        print(
            "TESTANDO LIGAS"
        )

        print(
            "=" * 100
        )

        for index, league in enumerate(
            leagues
        ):

            league_name = (
                league[
                    "name"
                ]
            )

            print(
                "\n"
                + "-" * 100
            )

            print(
                f"LIGA [{index}]"
            )

            print(
                league_name
            )

            card = (
                await find_league_card_by_name(
                    page,
                    league_name,
                )
            )

            if card is None:

                print(
                    "Card não encontrado "
                    "após reconsulta."
                )

                result[
                    "results"
                ].append(
                    {
                        "league":
                            league_name,

                        "clicked":
                            False,

                        "network":
                            [],
                    }
                )

                continue

            try:

                css_class = (
                    await card.get_attribute(
                        "class"
                    )
                    or ""
                )

            except Exception:

                css_class = ""

            currently_active = (
                "vcm-98c"
                in css_class.split()
            )

            print(
                "Class atual:",
                css_class,
            )

            print(
                "Ativa:",
                currently_active,
            )

            # =================================================
            # MARCA NETWORK
            # =================================================

            marker = (
                monitor.mark()
            )

            # =================================================
            # CLIQUE
            # =================================================

            if currently_active:

                print(
                    "Liga já está ativa."
                )

                clicked = False

            else:

                try:

                    await (
                        card
                        .scroll_into_view_if_needed()
                    )

                    await page.wait_for_timeout(
                        300
                    )

                    print(
                        "Clicando no card..."
                    )

                    await card.click(
                        timeout=8_000,
                    )

                    clicked = True

                except Exception as exc:

                    print(
                        "Erro clicando:"
                    )

                    print(
                        exc
                    )

                    clicked = False

            # =================================================
            # AGUARDA REDE / UI
            # =================================================

            await page.wait_for_timeout(
                5000
            )

            events = (
                monitor.since(
                    marker
                )
            )

            print(
                "\nNetwork após ação:"
            )

            print_network_events(
                events
            )

            # =================================================
            # VERIFICA ESTADO DEPOIS
            # =================================================

            card_after = (
                await find_league_card_by_name(
                    page,
                    league_name,
                )
            )

            active_after = False

            class_after = None

            if card_after:

                try:

                    class_after = (
                        await card_after.get_attribute(
                            "class"
                        )
                        or ""
                    )

                    active_after = (
                        "vcm-98c"
                        in class_after.split()
                    )

                except Exception:
                    pass

            print(
                "\nAtiva depois:",
                active_after,
            )

            print(
                "Classe depois:",
                class_after,
            )

            result[
                "results"
            ].append(
                {
                    "league":
                        league_name,

                    "clicked":
                        clicked,

                    "active_before":
                        currently_active,

                    "active_after":
                        active_after,

                    "class_before":
                        css_class,

                    "class_after":
                        class_after,

                    "network":
                        events,
                }
            )

            await page.wait_for_timeout(
                1000
            )

    # ========================================================
    # SAVE
    # ========================================================

    result[
        "finished_at"
    ] = now_iso()

    output_file.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "\n"
        + "=" * 100
    )

    print(
        "TESTE FINALIZADO"
    )

    print(
        "=" * 100
    )

    print(
        "Resultado:"
    )

    print(
        output_file
    )


# ============================================================
# ENTRYPOINT
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )
