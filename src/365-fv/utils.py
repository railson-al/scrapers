"""
Helpers puros (sem browser) compartilhados pelos scripts de src/365-fv.
"""

import hashlib
import json
import re

from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse


# ============================================================
# DATA/HORA E HASH
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


# ============================================================
# TEXTO E URL
# ============================================================


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


# ============================================================
# PD
# ============================================================


def parse_pd(pd: str | None):
    """
    Exemplo:

    #AC#B146#C20940364#D1#E139214584#F2#

    vira aproximadamente:

    {
        "AC": "",
        "B": "146",
        "C": "20940364",
        "D": "1",
        "E": "139214584",
        "F": "2"
    }

    Ainda não atribuímos significado definitivo
    para essas chaves.
    """

    if not pd:
        return {}

    parts = pd.split("#")

    result = {}

    for part in parts:

        if not part:
            continue

        match = re.match(
            r"^([A-Z]+)(.*)$",
            part,
        )

        if not match:
            continue

        key = match.group(1)

        value = match.group(2)

        # Caso uma chave apareça repetida,
        # preservamos tudo.
        if key in result:

            if not isinstance(
                result[key],
                list,
            ):
                result[key] = [
                    result[key]
                ]

            result[key].append(
                value
            )

        else:
            result[key] = value

    return result


# ============================================================
# JSON E RUNS
# ============================================================


def load_json(path: Path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def save_json(
    path: Path,
    data,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def find_latest_run(
    base_dir: Path,
):
    """
    Retorna o diretório de run mais recente
    (maior YYYYMMDD_HHMMSS) dentro de base_dir.
    """

    if not base_dir.exists():
        return None

    runs = [
        path
        for path in base_dir.iterdir()
        if path.is_dir()
    ]

    if not runs:
        return None

    return max(
        runs,
        key=lambda path: path.name,
    )


# ============================================================
# CLASSIFICAÇÃO DE REQUESTS
# ============================================================


def detect_response_type(url: str):
    """
    Tipo = nome do endpoint depois de /virtualsportscontentapi/
    ("splash", "coupon", ...). Endpoints ainda não mapeados (ex.:
    aba Resultados) também são capturados, com o próprio nome.
    None = fora da API.
    """

    parts = [
        part
        for part in urlparse(url).path.lower().split("/")
        if part
    ]

    if "virtualsportscontentapi" not in parts:
        return None

    index = parts.index(
        "virtualsportscontentapi"
    )

    if index + 1 >= len(parts):
        return "other"

    # Vira parte do nome do arquivo: só [a-z0-9_].
    return re.sub(
        r"[^a-z0-9]+",
        "_",
        parts[index + 1],
    ).strip("_") or "other"


def is_coupon_response(
    response,
):
    return (
        detect_response_type(
            response.url
        )
        == "coupon"
    )


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
