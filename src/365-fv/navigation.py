"""
Captura de rede (RawCollector) e navegação no site
compartilhadas por collector.py e collector_all.py.
"""

import asyncio
import itertools
import json
import re

from pathlib import Path

from config import EMPTY_COUPON_MARKER
from utils import (
    now_iso,
    sha256_text,
    parse_url_query,
    normalize_text,
    parse_pd,
    detect_response_type,
    is_coupon_response,
    extract_cookie_info,
)


# ============================================================
# RAW COLLECTOR
# ============================================================


class RawCollector:

    def __init__(
        self,
        output_dir: Path,
    ):
        self.output_dir = output_dir

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.sequence = itertools.count(
            1
        )

        # Resumo de cada coupon salvo,
        # usado para montar o run.json.
        self.coupons = []

        # ChallengeID (E) -> liga (C) em que
        # foi visto primeiro. Detecta coupons
        # de transição de liga (stale).
        self.league_by_challenge = {}

    def is_stale(
        self,
        league_id,
        challenge_id,
    ):
        """
        Ao trocar de liga, o frontend pede a
        liga nova (C) com o jogo da liga
        anterior (E), e o servidor responde
        pelo E. Um E já visto com outro C
        indica esse coupon de transição.
        """

        first_league = self.league_by_challenge.get(
            challenge_id
        )

        return (
            first_league is not None
            and first_league != league_id
        )

    def is_slot_coupon(
        self,
        response,
    ):
        if not is_coupon_response(
            response
        ):
            return False

        pd_tokens = parse_pd(
            parse_url_query(
                response.url
            ).get(
                "pd"
            )
        )

        return not self.is_stale(
            pd_tokens.get("C"),
            pd_tokens.get("E"),
        )

    async def log_request(
        self,
        request,
    ):
        url = request.url

        response_type = detect_response_type(
            url
        )

        if not response_type:
            return

        try:

            headers = (
                await request.all_headers()
            )

        except Exception:

            headers = request.headers

        query = parse_url_query(
            url
        )

        print(
            "\n"
            + "=" * 100
        )

        print(
            ">>> REQUEST"
        )

        print(
            "Type:",
            response_type.upper(),
        )

        print(
            "Method:",
            request.method,
        )

        print(
            "URL:",
            url,
        )

        print(
            "PD:",
            query.get(
                "pd"
            ),
        )

        x_request_id = headers.get(
            "x-request-id"
        )

        if x_request_id:

            print(
                "x-request-id:",
                x_request_id,
            )

        if headers.get(
            "x-net-sync-term"
        ):

            print(
                "x-net-sync-term: [present]"
            )

    async def capture_response(
        self,
        response,
    ):
        url = response.url

        response_type = detect_response_type(
            url
        )

        if not response_type:
            return

        request = response.request

        try:

            request_headers = (
                await request.all_headers()
            )

        except Exception:

            request_headers = (
                request.headers
            )

        try:

            response_headers = (
                await response.all_headers()
            )

        except Exception:

            response_headers = (
                response.headers
            )

        try:

            body = (
                await response.text()
            )

        except Exception as exc:

            print(
                "Erro lendo body:",
                exc,
            )

            return

        query = parse_url_query(
            url
        )

        sequence = next(
            self.sequence
        )

        raw_data = {

            "schema_version": 1,

            "sequence": sequence,

            "captured_at": (
                now_iso()
            ),

            "type": response_type,

            "request": {

                "method": (
                    request.method
                ),

                "url": (
                    url
                ),

                "resource_type": (
                    request.resource_type
                ),

                "query": (
                    query
                ),

                "pd": (
                    query.get(
                        "pd"
                    )
                ),

                "headers": {

                    "x-request-id": (
                        request_headers.get(
                            "x-request-id"
                        )
                    ),

                    "x-net-sync-term-present": bool(
                        request_headers.get(
                            "x-net-sync-term"
                        )
                    ),

                    "referer": (
                        request_headers.get(
                            "referer"
                        )
                    ),
                },

                "cookies": (
                    extract_cookie_info(
                        request_headers.get(
                            "cookie"
                        )
                    )
                ),
            },

            "response": {

                "status": (
                    response.status
                ),

                "status_text": (
                    response.status_text
                ),

                "headers": {

                    "content-type": (
                        response_headers.get(
                            "content-type"
                        )
                    ),

                    "content-length": (
                        response_headers.get(
                            "content-length"
                        )
                    ),
                },
            },

            "body": {

                "size": (
                    len(body)
                ),

                "sha256": (
                    sha256_text(
                        body
                    )
                ),

                "content": (
                    body
                ),
            },
        }

        filename = (
            f"{sequence:04d}_"
            f"{response_type}.json"
        )

        filepath = (
            self.output_dir
            / filename
        )

        filepath.write_text(
            json.dumps(
                raw_data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        empty = (
            not body
            or EMPTY_COUPON_MARKER in body
        )

        if response_type == "coupon":

            pd_tokens = parse_pd(
                query.get(
                    "pd"
                )
            )

            league_id = pd_tokens.get(
                "C"
            )

            challenge_id = pd_tokens.get(
                "E"
            )

            stale = self.is_stale(
                league_id,
                challenge_id,
            )

            self.league_by_challenge.setdefault(
                challenge_id,
                league_id,
            )

            # Início do jogo: CM=...~YYYYMMDDHHMMSS
            start = re.search(
                r"CM=[^;|]*~\d{8}(\d{2})(\d{2})",
                body,
            )

            self.coupons.append(
                {
                    "sequence": sequence,
                    "file": filename,
                    "league_id": league_id,
                    "challenge_id": challenge_id,
                    "start_time": (
                        f"{start.group(1)}:{start.group(2)}"
                        if start
                        else None
                    ),
                    "status": response.status,
                    "body_size": len(body),
                    "empty": empty,
                    "stale": stale,
                }
            )

        print(
            "\n"
            + "#" * 100
        )

        print(
            "<<< RESPONSE CAPTURADA"
        )

        print(
            "Sequence:",
            sequence,
        )

        print(
            "Type:",
            response_type.upper(),
        )

        print(
            "Status:",
            response.status,
        )

        print(
            "Body size:",
            len(body),
        )

        print(
            "PD:",
            query.get(
                "pd"
            ),
        )

        print(
            "Arquivo:",
            filepath,
        )

        if (
            response_type == "coupon"
            and empty
        ):
            print(
                "AVISO: coupon vazio "
                "(sem mercados)."
            )

        print(
            "#" * 100
        )


# ============================================================
# ESPORTES VIRTUAIS
# ============================================================


async def find_virtual_sports_entry(
    page,
    timeout_seconds=30,
):
    """
    Encontra "Esportes Virtuais" sem cair no strict mode.

    Prioridade:
    1. elemento visível fora da navegação lateral
    2. DIV visível
    3. qualquer elemento visível
    """

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

        try:

            count = (
                await locator.count()
            )

        except Exception:

            count = 0

        if count == 0:

            await page.wait_for_timeout(
                500
            )

            continue

        print(
            "Encontrados:",
            count,
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

                visible = (
                    await element.is_visible()
                )

                if not visible:
                    continue

                info = (
                    await element.evaluate(
                        """
                        (el) => {

                            const nav =
                                el.closest(
                                    'nav, [role="navigation"]'
                                );

                            const main =
                                el.closest(
                                    'main, [role="main"]'
                                );

                            return {

                                tag:
                                    el.tagName,

                                class:
                                    el.className
                                    || "",

                                inNavigation:
                                    !!nav,

                                inMain:
                                    !!main,

                                cursor:
                                    window
                                    .getComputedStyle(el)
                                    .cursor
                            };
                        }
                        """
                    )
                )

                candidates.append(
                    {
                        "index":
                            index,

                        "element":
                            element,

                        "tag":
                            info[
                                "tag"
                            ],

                        "class":
                            info[
                                "class"
                            ],

                        "in_navigation":
                            info[
                                "inNavigation"
                            ],

                        "in_main":
                            info[
                                "inMain"
                            ],

                        "cursor":
                            info[
                                "cursor"
                            ],
                    }
                )

            except Exception:
                continue

        print(
            "\nCandidatos visíveis:"
        )

        for item in candidates:

            print(
                f"[{item['index']}] "
                f"tag={item['tag']} "
                f"class={item['class']} "
                f"navigation={item['in_navigation']} "
                f"main={item['in_main']} "
                f"cursor={item['cursor']}"
            )

        # ====================================================
        # PRIORIDADE 1
        # Conteúdo principal e fora da navegação
        # ====================================================

        for item in candidates:

            if (
                item[
                    "in_main"
                ]
                and not item[
                    "in_navigation"
                ]
            ):

                print(
                    "\nSelecionado:"
                )

                print(
                    f"tag={item['tag']} "
                    f"class={item['class']}"
                )

                return item[
                    "element"
                ]

        # ====================================================
        # PRIORIDADE 2
        # Qualquer elemento fora da navegação
        # ====================================================

        for item in candidates:

            if not item[
                "in_navigation"
            ]:

                print(
                    "\nSelecionado fora "
                    "da navegação:"
                )

                print(
                    f"tag={item['tag']} "
                    f"class={item['class']}"
                )

                return item[
                    "element"
                ]

        # ====================================================
        # PRIORIDADE 3
        # DIV
        # ====================================================

        for item in candidates:

            if (
                item[
                    "tag"
                ].upper()
                == "DIV"
            ):

                print(
                    "\nSelecionado DIV:"
                )

                print(
                    item[
                        "class"
                    ]
                )

                return item[
                    "element"
                ]

        await page.wait_for_timeout(
            500
        )

    return None


# ============================================================
# DOM FUTEBOL
# ============================================================


async def inspect_element_tree(
    element,
    max_depth=8,
):
    try:

        return await element.evaluate(
            """
            (element, maxDepth) => {

                const result = [];

                let current = element;

                let depth = 0;

                while (
                    current &&
                    depth <= maxDepth
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

                        class:
                            current.className
                            || "",

                        role:
                            current.getAttribute(
                                "role"
                            ),

                        href:
                            current.getAttribute(
                                "href"
                            ),

                        tabindex:
                            current.getAttribute(
                                "tabindex"
                            ),

                        onclick:
                            current.getAttribute(
                                "onclick"
                            ),

                        cursor:
                            style.cursor,

                        text:
                            (
                                current.innerText
                                || ""
                            )
                            .trim()
                            .slice(
                                0,
                                100
                            )
                    });

                    current =
                        current.parentElement;

                    depth++;
                }

                return result;
            }
            """,
            max_depth,
        )

    except Exception:

        return []


def score_ancestor(
    info,
):
    score = 0

    tag = (
        info.get(
            "tag"
        )
        or ""
    ).upper()

    css_class = (
        info.get(
            "class"
        )
        or ""
    ).lower()

    role = (
        info.get(
            "role"
        )
        or ""
    ).lower()

    cursor = (
        info.get(
            "cursor"
        )
        or ""
    ).lower()

    if "lhs-" in css_class:
        return -1000

    if "vss-" in css_class:
        score += 100

    if tag in {
        "BUTTON",
        "A",
    }:
        score += 80

    if role in {
        "button",
        "link",
    }:
        score += 70

    if cursor == "pointer":
        score += 60

    if info.get(
        "onclick"
    ):
        score += 50

    if (
        info.get(
            "tabindex"
        )
        is not None
    ):
        score += 30

    score -= (
        info.get(
            "depth",
            0
        )
        * 3
    )

    return score


def ancestor_locator(
    locator,
    depth,
):
    result = locator

    for _ in range(
        depth
    ):

        result = result.locator(
            ".."
        )

    return result


# ============================================================
# FUTEBOL CANDIDATES
# ============================================================


async def find_football_click_candidates(
    page,
    timeout_seconds=30,
):
    print(
        "\nAguardando interface "
        "de Virtual Sports renderizar..."
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

        futebol = (
            page.get_by_text(
                "Futebol",
                exact=True,
            )
        )

        count = (
            await futebol.count()
        )

        if count == 0:

            await page.wait_for_timeout(
                500
            )

            continue

        print(
            "\nElementos 'Futebol' encontrados:",
            count,
        )

        candidates = []

        for index in range(
            count
        ):

            element = (
                futebol.nth(
                    index
                )
            )

            try:

                if not (
                    await element.is_visible()
                ):

                    continue

            except Exception:

                continue

            tree = (
                await inspect_element_tree(
                    element
                )
            )

            print(
                "\n"
                + "-" * 90
            )

            print(
                f"FUTEBOL [{index}]"
            )

            for info in tree:

                print(
                    f"depth={info['depth']} "
                    f"tag={info['tag']} "
                    f"class={info['class']} "
                    f"role={info['role']} "
                    f"cursor={info['cursor']}"
                )

                score = (
                    score_ancestor(
                        info
                    )
                )

                if score <= 0:
                    continue

                candidates.append(
                    {
                        "source_index":
                            index,

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
                                "class"
                            ],

                        "locator":
                            ancestor_locator(
                                element,
                                info[
                                    "depth"
                                ],
                            ),
                    }
                )

        if candidates:

            candidates.sort(
                key=lambda item:
                    item[
                        "score"
                    ],
                reverse=True,
            )

            print(
                "\nCandidatos de clique:"
            )

            for index, item in enumerate(
                candidates
            ):

                print(
                    f"[{index}] "
                    f"score={item['score']} "
                    f"source={item['source_index']} "
                    f"depth={item['depth']} "
                    f"tag={item['tag']} "
                    f"class={item['class']}"
                )

            return candidates

        await page.wait_for_timeout(
            500
        )

    return []


# ============================================================
# TESTE CLIQUE FUTEBOL
# ============================================================


async def click_football_and_wait(
    page,
    candidates,
):
    seen = set()

    for index, candidate in enumerate(
        candidates
    ):

        key = (
            candidate[
                "source_index"
            ],
            candidate[
                "depth"
            ],
            candidate[
                "class"
            ],
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        locator = (
            candidate[
                "locator"
            ]
        )

        print(
            "\n"
            + "=" * 100
        )

        print(
            f"TENTATIVA [{index}]"
        )

        print(
            "score:",
            candidate[
                "score"
            ],
        )

        print(
            "depth:",
            candidate[
                "depth"
            ],
        )

        print(
            "class:",
            candidate[
                "class"
            ],
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

                timeout=6_000,

            ) as splash_info:

                await locator.click(
                    timeout=5_000,
                )

            splash = (
                await splash_info.value
            )

            print(
                "\n✓ B146 detectado"
            )

            print(
                "Status:",
                splash.status,
            )

            # =================================================
            # COUPON
            # =================================================

            try:

                async with page.expect_response(

                    lambda response:
                        (
                            "/contentdata/"
                            "virtualsportscontentapi/"
                            "coupon"
                        )
                        in response.url.lower(),

                    timeout=30_000,

                ) as coupon_info:

                    # Muitas vezes o coupon já vem
                    # imediatamente após o splash.
                    await page.wait_for_timeout(
                        1
                    )

                coupon = (
                    await coupon_info.value
                )

            except Exception:

                print(
                    "B146 detectado, "
                    "mas coupon não foi "
                    "capturado nesta espera."
                )

                return (
                    splash,
                    None,
                )

            print(
                "✓ COUPON detectado"
            )

            print(
                "Status:",
                coupon.status,
            )

            return (
                splash,
                coupon,
            )

        except Exception:

            print(
                "Não disparou B146."
            )

    return (
        None,
        None,
    )


# ============================================================
# ÁREA PRINCIPAL
# ============================================================


async def get_main(
    page,
):
    for selector in (
        '[role="main"]',
        "main",
    ):
        locator = page.locator(
            selector
        )

        if await locator.count():
            return locator.first

    return page.locator(
        "body"
    )


# ============================================================
# LIGAS
# ============================================================


async def get_league_cards(
    page,
    timeout_seconds=15,
):
    """
    Cards de liga são div.vcm-d4.
    O card ativo possui a classe vcm-98c.
    """

    loop = asyncio.get_running_loop()

    deadline = (
        loop.time()
        + timeout_seconds
    )

    while loop.time() < deadline:

        main = await get_main(
            page
        )

        cards = main.locator(
            "div.vcm-d4"
        )

        result = []

        for index in range(
            await cards.count()
        ):
            card = cards.nth(
                index
            )

            try:
                if not await card.is_visible():
                    continue

                name = normalize_text(
                    await card.inner_text()
                )

                css_class = (
                    await card.get_attribute(
                        "class"
                    )
                    or ""
                )

            except Exception:
                continue

            if not name:
                continue

            result.append(
                {
                    "name": name,
                    "active": (
                        "vcm-98c"
                        in css_class.split()
                    ),
                    "locator": card,
                }
            )

        if result:
            return result

        await page.wait_for_timeout(
            500
        )

    return []


def print_league_cards(
    cards,
):
    print(
        "\nLigas disponíveis:"
    )

    for position, card in enumerate(
        cards,
        1,
    ):
        print(
            f"  [{position}]"
            + (" * " if card["active"] else "   ")
            + card["name"]
        )


async def activate_league_card(
    page,
    card,
):
    """
    Clica no card (se ainda não estiver
    ativo) e espera o coupon da liga.
    Retorna True em caso de sucesso.
    """

    if card["active"]:

        print(
            "\nLiga já ativa:",
            card["name"],
        )

        return True

    print(
        "\nSelecionando liga:",
        card["name"],
    )

    try:
        async with page.expect_response(
            is_coupon_response,
            timeout=15_000,
        ):
            await card["locator"].click(
                timeout=5_000,
            )

    except Exception as exc:

        print(
            "\nERRO selecionando liga:",
            exc,
        )

        return False

    # Aguarda a faixa de horários rerenderizar.
    await page.wait_for_timeout(
        2000
    )

    return True


# ============================================================
# HORÁRIOS
# ============================================================


async def find_results_anchor(
    page,
):
    """
    O texto "Resultados" serve de âncora
    geométrica para a linha de horários.
    """

    main = await get_main(
        page
    )

    locator = main.get_by_text(
        "Resultados",
        exact=True,
    )

    candidates = []

    for index in range(
        await locator.count()
    ):
        element = locator.nth(
            index
        )

        try:
            if not await element.is_visible():
                continue

            box = await element.bounding_box()

        except Exception:
            continue

        if box:
            candidates.append(
                box
            )

    if not candidates:
        return None

    # Se existirem vários, pega o mais alto.
    candidates.sort(
        key=lambda box: box["y"]
    )

    return candidates[0]


async def find_time_elements(
    page,
    text_pattern,
):
    """
    Elementos HH:MM visíveis na mesma linha
    e à direita de "Resultados", ordenados
    da esquerda para a direita.
    Reconsulta o DOM a cada chamada, pois
    a faixa pode rerenderizar.
    """

    anchor = await find_results_anchor(
        page
    )

    if not anchor:
        return []

    anchor_center_y = (
        anchor["y"]
        + anchor["height"] / 2
    )

    main = await get_main(
        page
    )

    locator = main.get_by_text(
        text_pattern,
        exact=True,
    )

    result = []

    for index in range(
        await locator.count()
    ):
        element = locator.nth(
            index
        )

        try:
            if not await element.is_visible():
                continue

            text = normalize_text(
                await element.inner_text()
            )

            box = await element.bounding_box()

        except Exception:
            continue

        if not box:
            continue

        if not re.fullmatch(
            r"\d{1,2}:\d{2}",
            text,
        ):
            continue

        center_y = (
            box["y"]
            + box["height"] / 2
        )

        if abs(
            center_y
            - anchor_center_y
        ) > 40:
            continue

        if box["x"] < anchor["x"]:
            continue

        result.append(
            {
                "time": text,
                "x": box["x"],
                "element": element,
            }
        )

    result.sort(
        key=lambda item: item["x"]
    )

    return result


async def discover_time_slots(
    page,
):
    items = await find_time_elements(
        page,
        re.compile(
            r"^\s*\d{1,2}:\d{2}\s*$"
        ),
    )

    # Dedup de clones visuais,
    # mantendo a ordem da esquerda
    # para a direita.
    slots = []

    for item in items:

        if item["time"] not in slots:
            slots.append(
                item["time"]
            )

    return slots


async def collect_time_slots(
    page,
    collector,
):
    """
    Clica em cada horário da liga ativa e
    espera o coupon daquele jogo antes do
    próximo clique. O horário já exibido
    não dispara request: nesse caso o jogo
    é o último coupon capturado.
    """

    slots = await discover_time_slots(
        page
    )

    print(
        "\nHorários detectados:",
        slots,
    )

    results = []

    for time_text in slots:

        entry = {
            "time": time_text,
            "league_id": None,
            "challenge_id": None,
            "requested": False,
        }

        results.append(
            entry
        )

        items = await find_time_elements(
            page,
            time_text,
        )

        if not items:

            # O jogo pode ter começado e
            # saído da faixa durante a coleta.
            print(
                f"\nHorário {time_text} "
                "não encontrado mais."
            )

            entry["error"] = "not found"

            continue

        print(
            f"\nClicando horário {time_text}..."
        )

        try:
            async with page.expect_response(
                collector.is_slot_coupon,
                timeout=6_000,
            ) as coupon_info:
                await items[0]["element"].click(
                    timeout=5_000,
                )

            coupon = await coupon_info.value

            pd_tokens = parse_pd(
                parse_url_query(
                    coupon.url
                ).get(
                    "pd"
                )
            )

            entry["requested"] = True
            entry["league_id"] = pd_tokens.get("C")
            entry["challenge_id"] = pd_tokens.get("E")

        except Exception:

            # As respostas podem chegar fora de
            # ordem: ignora coupons de transição.
            valid = [
                coupon
                for coupon in collector.coupons
                if not coupon["stale"]
            ]

            if valid:
                last = valid[-1]
                entry["league_id"] = last["league_id"]
                entry["challenge_id"] = last["challenge_id"]

            print(
                f"Horário {time_text} não "
                "disparou coupon (já exibido?). "
                "Usando último coupon:",
                entry["challenge_id"],
            )

        # Evita cliques em sequência rápida
        # demais, que cancelam requests.
        await page.wait_for_timeout(
            1000
        )

    return results


def attach_coupon_files(
    slots,
    coupons,
):
    """
    Liga cada horário ao arquivo do coupon
    salvo com a mesma liga (C) e o mesmo
    ChallengeID (E). O mesmo ChallengeID
    pode aparecer em ligas diferentes.
    Em duplicatas, vale o último coupon.
    """

    by_key = {
        (
            coupon["league_id"],
            coupon["challenge_id"],
        ): coupon
        for coupon in coupons
    }

    for slot in slots:

        coupon = by_key.get(
            (
                slot["league_id"],
                slot["challenge_id"],
            )
        )

        if coupon is None:
            continue

        slot["file"] = coupon["file"]
        slot["body_size"] = coupon["body_size"]
        slot["empty"] = coupon["empty"]

        # Confere o horário clicado com o
        # início do jogo no coupon (CM).
        # None quando o coupon veio vazio.
        slot["start_matches"] = (
            coupon["start_time"] == slot["time"]
            if coupon["start_time"]
            else None
        )
