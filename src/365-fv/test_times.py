import asyncio
import json
import re
import time

from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from camoufox.async_api import AsyncCamoufox


# ============================================================
# CONFIG
# ============================================================

BASE_URL = "https://www.bet365.bet.br/"

DATA_DIR = Path("data")

DIAGNOSTICS_DIR = (
    DATA_DIR
    / "diagnostics"
)


# ============================================================
# UTIL
# ============================================================

def now_iso():
    return (
        datetime.now()
        .astimezone()
        .isoformat()
    )


def normalize_text(
    value: str | None,
):
    if not value:
        return ""

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def parse_url_query(
    url: str,
):
    parsed = urlparse(
        url
    )

    query = parse_qs(
        parsed.query,
        keep_blank_values=True,
    )

    result = {}

    for key, values in query.items():

        if len(values) == 1:
            result[key] = values[0]

        else:
            result[key] = values

    return result


def parse_pd(
    pd: str | None,
):
    """
    Apenas tokeniza o PD para facilitar
    nossa comparação.

    Não atribui significado definitivo
    às chaves.
    """

    if not pd:
        return {}

    result = {}

    for part in pd.split("#"):

        if not part:
            continue

        match = re.match(
            r"^([A-Z]+)(.*)$",
            part,
        )

        if not match:
            continue

        result[
            match.group(1)
        ] = match.group(2)

    return result


def is_interesting_url(
    url: str,
):
    value = url.lower()

    return (
        "virtualsportscontentapi"
        in value

        or

        "/contentdata/"
        in value
    )


def classify_url(
    url: str,
):
    value = url.lower()

    if (
        "/virtualsportscontentapi/splash"
        in value
    ):
        return "splash"

    if (
        "/virtualsportscontentapi/coupon"
        in value
    ):
        return "coupon"

    if (
        "/contentdata/"
        in value
    ):
        return "contentdata"

    return "other"


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
            (
                time.monotonic()
                -
                self.started_at
            ),
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

        pd = query.get(
            "pd"
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
                    pd,

                "pd_tokens":
                    parse_pd(
                        pd
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

        pd = query.get(
            "pd"
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
                    pd,

                "pd_tokens":
                    parse_pd(
                        pd
                    ),
            }
        )


# ============================================================
# MAIN AREA
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

    locator = (
        page.locator(
            "main"
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
# LIGA ATIVA
# ============================================================

async def get_active_league(
    page,
):
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

            css_class = (
                await card.get_attribute(
                    "class"
                )
                or ""
            )

            if (
                "vcm-98c"
                not in css_class.split()
            ):
                continue

            name = normalize_text(
                await card.inner_text()
            )

            return {
                "index":
                    index,

                "name":
                    name,

                "class":
                    css_class,
            }

        except Exception:
            continue

    return None


# ============================================================
# RESULTADOS
# ============================================================

async def find_results_anchor(
    page,
):
    """
    Encontra o texto Resultados que serve
    de âncora geométrica para a linha de
    horários.
    """

    main = (
        await get_main(
            page
        )
    )

    locator = (
        main.get_by_text(
            "Resultados",
            exact=True,
        )
    )

    count = (
        await locator.count()
    )

    candidates = []

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

            box = (
                await element.bounding_box()
            )

            if not box:
                continue

            candidates.append(
                {
                    "element":
                        element,

                    "box":
                        box,

                    "class":
                        (
                            await element.get_attribute(
                                "class"
                            )
                            or ""
                        ),
                }
            )

        except Exception:
            continue

    if not candidates:
        return None

    # Normalmente existe apenas um.
    #
    # Se existirem vários, pegamos o mais
    # alto dentro da área principal.
    candidates.sort(
        key=lambda item:
            item[
                "box"
            ][
                "y"
            ]
    )

    return candidates[
        0
    ]


# ============================================================
# DESCOBRIR HORÁRIOS
# ============================================================

async def discover_time_slots(
    page,
):
    anchor = (
        await find_results_anchor(
            page
        )
    )

    if not anchor:

        print(
            "Texto 'Resultados' "
            "não encontrado."
        )

        return []

    anchor_box = (
        anchor[
            "box"
        ]
    )

    print(
        "\nÂncora Resultados:"
    )

    print(
        anchor_box
    )

    main = (
        await get_main(
            page
        )
    )

    # ========================================================
    # Procura qualquer texto no formato HH:MM
    # ========================================================

    locator = (
        main.get_by_text(
            re.compile(
                r"^\s*\d{1,2}:\d{2}\s*$"
            )
        )
    )

    count = (
        await locator.count()
    )

    result = []

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

            text = normalize_text(
                await element.inner_text()
            )

            if not re.fullmatch(
                r"\d{1,2}:\d{2}",
                text,
            ):
                continue

            box = (
                await element.bounding_box()
            )

            if not box:
                continue

            # =================================================
            # Deve estar aproximadamente na mesma linha
            # horizontal do "Resultados".
            # =================================================

            center_y = (
                box[
                    "y"
                ]
                +
                (
                    box[
                        "height"
                    ]
                    / 2
                )
            )

            anchor_center_y = (
                anchor_box[
                    "y"
                ]
                +
                (
                    anchor_box[
                        "height"
                    ]
                    / 2
                )
            )

            if abs(
                center_y
                -
                anchor_center_y
            ) > 40:

                continue

            # Os horários devem ficar à direita
            # de Resultados.
            if (
                box[
                    "x"
                ]
                <
                anchor_box[
                    "x"
                ]
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

                        cursor:
                            window
                            .getComputedStyle(el)
                            .cursor
                    })
                    """
                )
            )

            result.append(
                {
                    "name":
                        text,

                    "tag":
                        info[
                            "tag"
                        ],

                    "class":
                        info[
                            "className"
                        ],

                    "cursor":
                        info[
                            "cursor"
                        ],

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
                }
            )

        except Exception:
            continue

    # ========================================================
    # DEDUP
    # ========================================================

    unique = {}

    for item in result:

        name = (
            item[
                "name"
            ]
        )

        if name not in unique:

            unique[
                name
            ] = item

            continue

        # Em caso de clones visuais,
        # prefere o mais à esquerda.
        if (
            item[
                "x"
            ]
            <
            unique[
                name
            ][
                "x"
            ]
        ):

            unique[
                name
            ] = item

    result = list(
        unique.values()
    )

    result.sort(
        key=lambda item:
            item[
                "x"
            ]
    )

    return result


# ============================================================
# REENCONTRAR HORÁRIO
# ============================================================

async def find_time_element(
    page,
    time_text,
):
    """
    Reconsulta o DOM antes de cada clique,
    pois a faixa pode rerenderizar.
    """

    anchor = (
        await find_results_anchor(
            page
        )
    )

    if not anchor:
        return None

    anchor_box = (
        anchor[
            "box"
        ]
    )

    main = (
        await get_main(
            page
        )
    )

    locator = (
        main.get_by_text(
            time_text,
            exact=True,
        )
    )

    count = (
        await locator.count()
    )

    candidates = []

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

            box = (
                await element.bounding_box()
            )

            if not box:
                continue

            center_y = (
                box[
                    "y"
                ]
                +
                box[
                    "height"
                ]
                / 2
            )

            anchor_center_y = (
                anchor_box[
                    "y"
                ]
                +
                anchor_box[
                    "height"
                ]
                / 2
            )

            if abs(
                center_y
                -
                anchor_center_y
            ) > 40:

                continue

            candidates.append(
                {
                    "element":
                        element,

                    "box":
                        box,
                }
            )

        except Exception:
            continue

    if not candidates:
        return None

    candidates.sort(
        key=lambda item:
            item[
                "box"
            ][
                "x"
            ]
    )

    return candidates[
        0
    ][
        "element"
    ]


# ============================================================
# CLICK TARGET
# ============================================================

async def find_click_target(
    element,
):
    """
    Horário pode estar dentro de um wrapper
    clicável.

    Inspeciona até quatro ancestrais.
    """

    try:

        tree = (
            await element.evaluate(
                """
                el => {

                    const result = [];

                    let current = el;

                    let depth = 0;

                    while (
                        current
                        &&
                        depth <= 4
                    ) {

                        const style =
                            window.getComputedStyle(
                                current
                            );

                        result.push({

                            depth:
                                depth,

                            tag:
                                current.tagName,

                            className:
                                current.className || "",

                            cursor:
                                style.cursor,

                            role:
                                current.getAttribute(
                                    "role"
                                ),

                            tabindex:
                                current.getAttribute(
                                    "tabindex"
                                )
                        });

                        current =
                            current.parentElement;

                        depth++;
                    }

                    return result;
                }
                """
            )
        )

    except Exception:

        return element, {
            "depth": 0,
            "score": 0,
        }

    possibilities = []

    for info in tree:

        score = 0

        if (
            info[
                "cursor"
            ]
            == "pointer"
        ):
            score += 100

        if (
            info[
                "tag"
            ]
            in {
                "BUTTON",
                "A",
            }
        ):
            score += 80

        if (
            info[
                "role"
            ]
            in {
                "button",
                "tab",
                "link",
            }
        ):
            score += 70

        if (
            info[
                "tabindex"
            ]
            is not None
        ):
            score += 30

        # O próprio elemento ainda recebe
        # algum score para servir como fallback.
        if (
            info[
                "depth"
            ]
            == 0
        ):
            score += 10

        score -= (
            info[
                "depth"
            ]
            * 5
        )

        target = element

        for _ in range(
            info[
                "depth"
            ]
        ):

            target = (
                target.locator(
                    ".."
                )
            )

        possibilities.append(
            {
                "target":
                    target,

                "depth":
                    info[
                        "depth"
                    ],

                "score":
                    score,

                "tag":
                    info[
                        "tag"
                    ],

                "class":
                    info[
                        "className"
                    ],

                "cursor":
                    info[
                        "cursor"
                    ],
            }
        )

    possibilities.sort(
        key=lambda item:
            item[
                "score"
            ],
        reverse=True,
    )

    best = (
        possibilities[
            0
        ]
    )

    return (
        best[
            "target"
        ],
        best,
    )


# ============================================================
# NETWORK PRINT
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

            tokens = (
                event.get(
                    "pd_tokens"
                )
                or {}
            )

            interesting = {
                key: tokens.get(
                    key
                )
                for key in (
                    "B",
                    "C",
                    "E",
                    "L",
                    "K",
                    "M",
                    "X",
                )
                if key in tokens
            }

            print(
                "      tokens:",
                interesting,
            )


# ============================================================
# MAIN
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
        / "times.json"
    )

    print(
        "\n"
        + "=" * 100
    )

    print(
        "TEST TIMES"
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

    result = {

        "run_id":
            run_id,

        "started_at":
            now_iso(),

        "league":
            None,

        "times":
            [],

        "results":
            [],
    }

    # ========================================================
    # BROWSER
    # ========================================================

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
        # ESPORTES VIRTUAIS
        # ====================================================

        virtual_sports = (
            await find_virtual_sports_entry(
                page
            )
        )

        if virtual_sports is None:

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
        # FUTEBOL
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

        # Aguarda coupon/layout inicial.
        await page.wait_for_timeout(
            3000
        )

        # ====================================================
        # LIGA ATIVA
        # ====================================================

        active_league = (
            await get_active_league(
                page
            )
        )

        result[
            "league"
        ] = active_league

        print(
            "\n"
            + "=" * 100
        )

        print(
            "LIGA ATIVA"
        )

        print(
            "=" * 100
        )

        if active_league:

            print(
                active_league[
                    "name"
                ]
            )

        else:

            print(
                "Não identificada."
            )

        # ====================================================
        # DESCOBRE HORÁRIOS
        # ====================================================

        times = (
            await discover_time_slots(
                page
            )
        )

        result[
            "times"
        ] = times

        print(
            "\n"
            + "=" * 100
        )

        print(
            "HORÁRIOS DETECTADOS"
        )

        print(
            "=" * 100
        )

        if not times:

            print(
                "Nenhum horário encontrado."
            )

            return

        for index, item in enumerate(
            times
        ):

            print(
                f"[{index}] "
                f"{item['name']} "
                f"class={item['class']} "
                f"x={item['x']} "
                f"y={item['y']}"
            )

        # ====================================================
        # TESTA CADA HORÁRIO
        # ====================================================

        print(
            "\n"
            + "=" * 100
        )

        print(
            "TESTANDO HORÁRIOS"
        )

        print(
            "=" * 100
        )

        for index, item in enumerate(
            times
        ):

            time_text = (
                item[
                    "name"
                ]
            )

            print(
                "\n"
                + "-" * 100
            )

            print(
                f"HORÁRIO [{index}]"
            )

            print(
                time_text
            )

            element = (
                await find_time_element(
                    page,
                    time_text,
                )
            )

            if element is None:

                print(
                    "Elemento não encontrado."
                )

                result[
                    "results"
                ].append(
                    {
                        "time":
                            time_text,

                        "clicked":
                            False,

                        "reason":
                            "element not found",

                        "network":
                            [],
                    }
                )

                continue

            (
                click_target,
                target_info,
            ) = (
                await find_click_target(
                    element
                )
            )

            print(
                "Target:"
            )

            print(
                "  tag:",
                target_info.get(
                    "tag"
                ),
            )

            print(
                "  class:",
                target_info.get(
                    "class"
                ),
            )

            print(
                "  depth:",
                target_info.get(
                    "depth"
                ),
            )

            print(
                "  cursor:",
                target_info.get(
                    "cursor"
                ),
            )

            print(
                "  score:",
                target_info.get(
                    "score"
                ),
            )

            marker = (
                monitor.mark()
            )

            try:

                await (
                    click_target
                    .scroll_into_view_if_needed()
                )

                await page.wait_for_timeout(
                    250
                )

                print(
                    "Clicando..."
                )

                await click_target.click(
                    timeout=8_000,
                )

                clicked = True

            except Exception as exc:

                print(
                    "Erro no clique:"
                )

                print(
                    exc
                )

                clicked = False

            # =================================================
            # Observa transição.
            # =================================================

            await page.wait_for_timeout(
                3000
            )

            events = (
                monitor.since(
                    marker
                )
            )

            print(
                "\nNetwork:"
            )

            print_network_events(
                events
            )

            coupon_requests = [
                event
                for event in events
                if (
                    event[
                        "direction"
                    ]
                    == "request"
                    and
                    event[
                        "type"
                    ]
                    == "coupon"
                )
            ]

            result[
                "results"
            ].append(
                {
                    "time":
                        time_text,

                    "clicked":
                        clicked,

                    "click_target":
                        {
                            "tag":
                                target_info.get(
                                    "tag"
                                ),

                            "class":
                                target_info.get(
                                    "class"
                                ),

                            "depth":
                                target_info.get(
                                    "depth"
                                ),

                            "cursor":
                                target_info.get(
                                    "cursor"
                                ),

                            "score":
                                target_info.get(
                                    "score"
                                ),
                        },

                    "coupon_request_count":
                        len(
                            coupon_requests
                        ),

                    "network":
                        events,
                }
            )

            await page.wait_for_timeout(
                500
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