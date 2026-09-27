import asyncio
import hashlib
import itertools
import json
import re

from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from camoufox.async_api import AsyncCamoufox


# ============================================================
# CONFIG
# ============================================================

BASE_URL = "https://www.bet365.bet.br/"

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"


# ============================================================
# UTIL
# ============================================================

def now_iso():
    return datetime.now().astimezone().isoformat()


def sha256_text(value: str):
    return hashlib.sha256(
        value.encode(
            "utf-8",
            errors="replace",
        )
    ).hexdigest()


def parse_url_query(url: str):
    parsed = urlparse(url)

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


def extract_cookie_info(
    cookie_header: str | None,
):
    if not cookie_header:

        return {
            "names": [],
            "fingerprint": None,
        }

    names = []

    for item in cookie_header.split(";"):

        item = item.strip()

        if "=" not in item:
            continue

        names.append(
            item.split(
                "=",
                1,
            )[0]
        )

    return {
        "names": names,
        "fingerprint": sha256_text(
            cookie_header
        ),
    }


def detect_response_type(url: str):
    url_lower = url.lower()

    if (
        "/virtualsportscontentapi/splash"
        in url_lower
    ):
        return "splash"

    if (
        "/virtualsportscontentapi/coupon"
        in url_lower
    ):
        return "coupon"

    return None


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
# MAIN
# ============================================================

async def main():

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
        # COLETA
        # ====================================================

        print(
            "\n"
            + "=" * 100
        )

        print(
            "COLETA ATIVA"
        )

        print(
            "=" * 100
        )

        print(
            "Diretório:"
        )

        print(
            run_dir
        )

        await page.wait_for_timeout(
            60_000
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