import argparse
import re

from datetime import datetime
from fractions import Fraction
from pathlib import Path

from config import RAW_DIR, PARSED_DIR
from utils import (
    parse_pd,
    load_json,
    save_json,
    find_latest_run,
)


# ============================================================
# ODDS
# ============================================================

def fractional_to_decimal(
    value: str | None,
):
    """
    Converte:

    11/8 -> 2.375
    5/2  -> 3.5

    Mantemos também a odd original.
    """

    if not value:
        return None

    if "/" not in value:
        return None

    try:

        fraction = Fraction(
            value
        )

        return round(
            1 + float(fraction),
            6,
        )

    except Exception:
        return None


# ============================================================
# DATA/HORA
# ============================================================

def parse_datetime_from_cm(
    value: str | None,
):
    """
    Exemplo observado:

    Lista da Partida~20260926191900

    Extrai:

    2026-09-26T19:19:00

    Não colocamos timezone aqui ainda porque
    precisamos confirmar a semântica dessa data
    no protocolo.
    """

    if not value:
        return None

    match = re.search(
        r"(\d{14})",
        value,
    )

    if not match:
        return None

    raw_datetime = match.group(1)

    try:

        parsed = datetime.strptime(
            raw_datetime,
            "%Y%m%d%H%M%S",
        )

        return parsed.isoformat()

    except ValueError:
        return None


# ============================================================
# PROTOCOLO BET365
# ============================================================

def parse_record(
    raw_record: str,
):
    """
    Exemplo:

    PA;ID=87439151;NA=França;OD=11/8;

    vira:

    {
        "type": "PA",
        "fields": {
            "ID": "87439151",
            "NA": "França",
            "OD": "11/8"
        }
    }
    """

    raw_record = raw_record.strip()

    if not raw_record:
        return None

    parts = raw_record.split(";")

    record_type = parts[0].strip()

    fields = {}

    unnamed = []

    for part in parts[1:]:

        part = part.strip()

        if not part:
            continue

        if "=" in part:

            key, value = part.split(
                "=",
                1,
            )

            key = key.strip()

            value = value.strip()

            if key in fields:

                if not isinstance(
                    fields[key],
                    list,
                ):
                    fields[key] = [
                        fields[key]
                    ]

                fields[key].append(
                    value
                )

            else:
                fields[key] = value

        else:

            unnamed.append(
                part
            )

    result = {
        "type": record_type,
        "fields": fields,
    }

    if unnamed:
        result["unnamed"] = unnamed

    return result


def parse_protocol(
    body: str,
):
    """
    Primeiro estágio do parser.

    Apenas transforma:

    F|CL;...|EV;...|MG;...|PA;...|

    em uma lista genérica de registros.

    Nada é descartado.
    """

    raw_records = body.split("|")

    records = []

    for raw_record in raw_records:

        parsed = parse_record(
            raw_record
        )

        if parsed:
            records.append(
                parsed
            )

    return records


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def build_selection(
    record,
):
    fields = record["fields"]

    odds_fractional = fields.get(
        "OD"
    )

    return {
        "record_type": "PA",

        "id": fields.get(
            "ID"
        ),

        "name": fields.get(
            "NA"
        ),

        "odds": {
            "fractional": odds_fractional,

            "decimal": fractional_to_decimal(
                odds_fractional
            ),
        },

        "raw_fields": fields,
    }


def build_market(
    record,
):
    fields = record["fields"]

    return {
        "record_type": record["type"],

        "id": fields.get(
            "ID"
        ),

        "name": fields.get(
            "NA"
        ),

        "selections": [],

        "raw_fields": fields,
    }


def build_event(
    record,
):
    fields = record["fields"]

    cm = fields.get(
        "CM"
    )

    return {
        "record_type": "EV",

        "id": fields.get(
            "ID"
        ),

        "fixture_id": fields.get(
            "FI"
        ),

        "name": fields.get(
            "NA"
        ),

        "schedule_raw": cm,

        "start_time": parse_datetime_from_cm(
            cm
        ),

        "streaming": fields.get(
            "SI"
        ),

        "market_groups": [],

        "raw_fields": fields,
    }


def build_competition(
    record,
):
    fields = record["fields"]

    return {
        "record_type": "CL",

        "id": (
            fields.get("ID")
            or fields.get("CL")
        ),

        "code": fields.get(
            "CL"
        ),

        "name": fields.get(
            "NA"
        ),

        "events": [],

        "raw_fields": fields,
    }


# ============================================================
# ÁRVORE
# ============================================================

def build_hierarchy(
    records,
):
    """
    Hierarquia provisória baseada nos registros observados:

    CL
      EV
        MG
          MA
            PA

    Mas o protocolo pode apresentar PA diretamente em MG.
    Por isso tratamos ambos os casos.
    """

    competitions = []

    unknown_records = []

    current_competition = None

    current_event = None

    current_market_group = None

    current_market = None

    for record in records:

        record_type = record["type"]

        # ====================================================
        # F
        # ====================================================

        if record_type == "F":
            continue

        # ====================================================
        # CL
        # ====================================================

        if record_type == "CL":

            current_competition = (
                build_competition(
                    record
                )
            )

            competitions.append(
                current_competition
            )

            current_event = None

            current_market_group = None

            current_market = None

            continue

        # ====================================================
        # EV
        # ====================================================

        if record_type == "EV":

            current_event = (
                build_event(
                    record
                )
            )

            if current_competition:

                current_competition[
                    "events"
                ].append(
                    current_event
                )

            else:

                unknown_records.append(
                    record
                )

            current_market_group = None

            current_market = None

            continue

        # ====================================================
        # MG
        # ====================================================

        if record_type == "MG":

            current_market_group = (
                build_market(
                    record
                )
            )

            current_market_group[
                "markets"
            ] = []

            if current_event:

                current_event[
                    "market_groups"
                ].append(
                    current_market_group
                )

            else:

                unknown_records.append(
                    record
                )

            current_market = None

            continue

        # ====================================================
        # MA
        # ====================================================

        if record_type == "MA":

            current_market = (
                build_market(
                    record
                )
            )

            if current_market_group:

                current_market_group[
                    "markets"
                ].append(
                    current_market
                )

            elif current_event:

                # Caso o protocolo não tenha MG.
                current_event[
                    "market_groups"
                ].append(
                    {
                        "record_type": "synthetic",
                        "id": None,
                        "name": None,
                        "raw_fields": {},
                        "markets": [
                            current_market
                        ],
                        "selections": [],
                    }
                )

            else:

                unknown_records.append(
                    record
                )

            continue

        # ====================================================
        # PA
        # ====================================================

        if record_type == "PA":

            selection = build_selection(
                record
            )

            # Preferimos associar ao MA
            if current_market:

                current_market[
                    "selections"
                ].append(
                    selection
                )

            # Caso não haja MA,
            # associa diretamente ao MG.
            elif current_market_group:

                current_market_group[
                    "selections"
                ].append(
                    selection
                )

            else:

                unknown_records.append(
                    record
                )

            continue

        # ====================================================
        # DESCONHECIDO
        # ====================================================

        unknown_records.append(
            record
        )

    return {
        "competitions": competitions,
        "unknown_records": unknown_records,
    }


# ============================================================
# PARSER DE COUPON
# ============================================================

def parse_coupon(
    raw_data,
):
    body_data = raw_data.get(
        "body",
        {},
    )

    body = body_data.get(
        "content",
        "",
    )

    records = parse_protocol(
        body
    )

    hierarchy = build_hierarchy(
        records
    )

    request = raw_data.get(
        "request",
        {},
    )

    pd = request.get(
        "pd"
    )

    return {

        "schema_version": 1,

        "source": {

            "sequence": raw_data.get(
                "sequence"
            ),

            "captured_at": raw_data.get(
                "captured_at"
            ),

            "url": request.get(
                "url"
            ),

            "pd": pd,

            "pd_tokens": parse_pd(
                pd
            ),

            "body_sha256": body_data.get(
                "sha256"
            ),
        },

        "summary": {

            "record_count": len(
                records
            ),

            "competition_count": len(
                hierarchy[
                    "competitions"
                ]
            ),

            "event_count": sum(
                len(
                    competition[
                        "events"
                    ]
                )
                for competition
                in hierarchy[
                    "competitions"
                ]
            ),

            "unknown_record_count": len(
                hierarchy[
                    "unknown_records"
                ]
            ),
        },

        "competitions": hierarchy[
            "competitions"
        ],

        # Muito importante durante engenharia reversa:
        #
        # guardamos os registros ainda não entendidos.
        "unknown_records": hierarchy[
            "unknown_records"
        ],

        # Também guardamos todos os registros já
        # tokenizados para inspeção.
        "records": records,
    }


# ============================================================
# RESULTADOS
# ============================================================

def parse_results(
    raw_data,
):
    """
    Corpo de virtualsportscontentapi/results
    (aba Resultados). Cada jogo encerrado é um
    MG com N2 (mandante), N3 (visitante),
    SS (placar "casa#fora"), SM (horário H.MM)
    e NA (liga), seguido de MA e dos PA com as
    seleções vencedoras (EX = mercado).

    O MG;ID=MEET de cabeçalho não é jogo, mas
    continua em records, como todo o resto.
    """

    body_data = raw_data.get(
        "body",
        {},
    )

    records = parse_protocol(
        body_data.get(
            "content",
            "",
        )
    )

    results = []

    unknown_records = []

    current = None

    for record in records:

        record_type = record["type"]

        fields = record["fields"]

        if record_type == "MG" and "N2" in fields:

            current = {
                "fields": fields,
                "market": None,
                "selections": [],
            }

            results.append(
                current
            )

        elif record_type == "MG":

            # Cabeçalho (MEET): encerra o jogo atual.
            current = None

        elif record_type == "MA" and current:

            current["market"] = fields

        elif record_type == "PA" and current:

            current["selections"].append(
                {
                    **fields,
                    "odds_decimal": fractional_to_decimal(
                        fields.get(
                            "OD"
                        )
                    ),
                }
            )

        elif record_type not in (
            "F",
            "CL",
            "EV",
        ):
            unknown_records.append(
                record
            )

    request = raw_data.get(
        "request",
        {},
    )

    pd = request.get(
        "pd"
    )

    return {

        "schema_version": 1,

        "kind": "results",

        "source": {

            "sequence": raw_data.get(
                "sequence"
            ),

            "captured_at": raw_data.get(
                "captured_at"
            ),

            "url": request.get(
                "url"
            ),

            "pd": pd,

            "pd_tokens": parse_pd(
                pd
            ),

            "body_sha256": body_data.get(
                "sha256"
            ),
        },

        "summary": {

            "record_count": len(
                records
            ),

            "result_count": len(
                results
            ),

            "unknown_record_count": len(
                unknown_records
            ),
        },

        "results": results,

        "unknown_records": unknown_records,

        "records": records,
    }


# ============================================================
# PROCESSAMENTO DE ARQUIVO
# ============================================================

def parse_file(
    input_file: Path,
    output_file: Path,
):
    raw_data = load_json(
        input_file
    )

    if raw_data.get("type") == "results":

        parsed = parse_results(
            raw_data
        )

        save_json(
            output_file,
            parsed,
        )

        print(
            "\n✓",
            input_file.name,
        )

        print(
            "  Resultados:",
            parsed["summary"]["result_count"],
        )

        print(
            "  Output:",
            output_file,
        )

        return True

    if raw_data.get("type") != "coupon":

        print(
            "Ignorando:",
            input_file.name,
            "(não é coupon nem results)",
        )

        return False

    parsed = parse_coupon(
        raw_data
    )

    save_json(
        output_file,
        parsed,
    )

    summary = parsed[
        "summary"
    ]

    print(
        "\n✓",
        input_file.name,
    )

    print(
        "  Records:",
        summary[
            "record_count"
        ],
    )

    print(
        "  Competitions:",
        summary[
            "competition_count"
        ],
    )

    print(
        "  Events:",
        summary[
            "event_count"
        ],
    )

    print(
        "  Unknown:",
        summary[
            "unknown_record_count"
        ],
    )

    print(
        "  Output:",
        output_file,
    )

    return True


# ============================================================
# PROCESSAMENTO DE RUN
# ============================================================

def parse_run(
    run_dir: Path,
):
    run_id = run_dir.name

    output_dir = (
        PARSED_DIR
        / run_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # *_results.json = aba Resultados.
    coupon_files = sorted(
        [
            *run_dir.glob(
                "*_coupon.json"
            ),
            *run_dir.glob(
                "*_results.json"
            ),
        ]
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
        "\nRun:"
    )

    print(
        run_id
    )

    print(
        "\nCoupons encontrados:",
        len(coupon_files),
    )

    processed = 0

    for input_file in coupon_files:

        output_file = (
            output_dir
            / input_file.name
        )

        if parse_file(
            input_file,
            output_file,
        ):
            processed += 1

    print(
        "\n"
        + "=" * 80
    )

    print(
        "PARSER FINALIZADO"
    )

    print(
        "=" * 80
    )

    print(
        "Processados:",
        processed,
    )

    print(
        "Output:"
    )

    print(
        output_dir
    )


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Parser dos coupons "
            "Bet365 Virtual Sports"
        )
    )

    parser.add_argument(
        "--run",
        type=str,
        help=(
            "Diretório da execução "
            "em data/raw/"
        ),
    )

    parser.add_argument(
        "--file",
        type=str,
        help=(
            "Processa somente um "
            "arquivo *_coupon.json "
            "ou *_results.json"
        ),
    )

    args = parser.parse_args()

    # ========================================================
    # ARQUIVO ESPECÍFICO
    # ========================================================

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

        run_id = (
            input_file.parent.name
        )

        output_file = (
            PARSED_DIR
            / run_id
            / input_file.name
        )

        parse_file(
            input_file,
            output_file,
        )

        return

    # ========================================================
    # RUN ESPECÍFICO
    # ========================================================

    if args.run:

        run_dir = Path(
            args.run
        )

        if not run_dir.exists():

            # Permite passar apenas:
            #
            # 20260926_153500
            #
            candidate = (
                RAW_DIR
                / args.run
            )

            if candidate.exists():
                run_dir = candidate

            else:

                print(
                    "Run não encontrado:"
                )

                print(
                    args.run
                )

                return

    # ========================================================
    # ÚLTIMA RUN
    # ========================================================

    else:

        run_dir = find_latest_run(RAW_DIR)

        if run_dir is None:

            print(
                "Nenhuma execução encontrada em:"
            )

            print(
                RAW_DIR
            )

            return

        print(
            "Usando automaticamente "
            "a execução mais recente:"
        )

        print(
            run_dir
        )

    parse_run(
        run_dir
    )


# ============================================================
# ENTRYPOINT
# ============================================================

if __name__ == "__main__":
    main()
