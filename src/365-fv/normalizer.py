import argparse
import re

from pathlib import Path

from config import PARSED_DIR, NORMALIZED_DIR
from utils import (
    load_json,
    save_json,
    find_latest_run,
)


# ============================================================
# GRUPOS ONDE O LABEL PODE SER PROPAGADO POR POSIÇÃO
# ============================================================

POSITIONAL_LABEL_GROUPS = {
    "Gols Mais/Menos",
    "Para o Time Marcar - Sim/Não",
    "Resultado/Ambos Marcam",
    "Margem de Vitória",
    "Time -  Gols",
    "Time a Marcar",
}


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def canonical_selection_id(
    value: str | None,
):
    """
    Exemplos:

    PC87473102 -> 87473102
    TD87473112 -> 87473112
    87473102   -> 87473102
    """

    if not value:
        return None

    value = str(value)

    match = re.search(
        r"(\d+)$",
        value,
    )

    if not match:
        return value

    return match.group(1)


# ============================================================
# LABEL MAP POR ID
# ============================================================

def build_selection_label_map(
    market_group,
):
    """
    Captura labels auxiliares como:

    PC87473102 -> 0.5
    TD87473112 -> Ambos os Times

    e normaliza o ID:

    87473102 -> 0.5
    """

    labels = {}

    for market in market_group.get(
        "markets",
        [],
    ):

        for selection in market.get(
            "selections",
            [],
        ):

            selection_id = (
                canonical_selection_id(
                    selection.get("id")
                )
            )

            name = clean_text(
                selection.get("name")
            )

            odds = (
                selection.get(
                    "odds",
                    {},
                )
                or {}
            )

            # Registros auxiliares geralmente
            # possuem label mas não possuem odd.
            if (
                selection_id
                and name
                and odds.get(
                    "fractional"
                )
                is None
            ):
                labels[
                    selection_id
                ] = name

    return labels


# ============================================================
# LABELS POR POSIÇÃO
# ============================================================

def build_positional_label_templates(
    market_group,
):
    """
    Alguns mercados possuem IDs diferentes entre as colunas,
    mas a posição representa a mesma seleção.

    Exemplo:

    Mais de:
        0.5
        1.5
        2.5
        3.5

    Menos de:
        null
        null
        null
        null

    Nesse caso podemos usar:

        posição 0 -> 0.5
        posição 1 -> 1.5
        posição 2 -> 2.5
        posição 3 -> 3.5

    Essa inferência só é aplicada aos grupos conhecidos
    definidos em POSITIONAL_LABEL_GROUPS.
    """

    group_name = clean_text(
        market_group.get("name")
    )

    if (
        group_name
        not in POSITIONAL_LABEL_GROUPS
    ):
        return {}

    templates = {}

    for market in market_group.get(
        "markets",
        [],
    ):

        selections = market.get(
            "selections",
            [],
        )

        if not selections:
            continue

        names = []

        valid = True

        for selection in selections:

            name = clean_text(
                selection.get("name")
            )

            if not name:
                valid = False
                break

            names.append(
                name
            )

        if not valid:
            continue

        selection_count = len(
            selections
        )

        # Mantém o primeiro template encontrado.
        if (
            selection_count
            not in templates
        ):
            templates[
                selection_count
            ] = names

    return templates


# ============================================================
# HANDICAP
# ============================================================

def extract_handicap(
    selection,
):
    raw_fields = (
        selection.get(
            "raw_fields",
            {},
        )
        or {}
    )

    handicap = clean_text(
        raw_fields.get(
            "HA"
        )
    )

    if handicap is not None:
        return handicap

    return clean_text(
        raw_fields.get(
            "HD"
        )
    )


# ============================================================
# SELECTION
# ============================================================

def normalize_selection(
    selection,
    label_map,
    positional_labels,
    position,
    event_fixture_id,
):
    selection_id = (
        canonical_selection_id(
            selection.get("id")
        )
    )

    original_name = clean_text(
        selection.get(
            "name"
        )
    )

    exact_label = (
        label_map.get(
            selection_id
        )
    )

    positional_label = None

    if (
        positional_labels
        and position
        < len(
            positional_labels
        )
    ):
        positional_label = (
            positional_labels[
                position
            ]
        )

    handicap = extract_handicap(
        selection
    )

    # ========================================================
    # NOME FINAL
    # ========================================================

    name = (
        original_name
        or exact_label
        or positional_label
        or handicap
    )

    odds = (
        selection.get(
            "odds",
            {},
        )
        or {}
    )

    raw_fields = (
        selection.get(
            "raw_fields",
            {},
        )
        or {}
    )

    fixture_id = (
        clean_text(
            raw_fields.get(
                "FI"
            )
        )
        or event_fixture_id
    )

    return {
        "id": selection_id,

        "name": name,

        "label": (
            exact_label
            or positional_label
        ),

        "handicap": handicap,

        "odds_fractional": (
            odds.get(
                "fractional"
            )
        ),

        "odds_decimal": (
            odds.get(
                "decimal"
            )
        ),

        "fixture_id": fixture_id,

        "suspended": (
            raw_fields.get(
                "SU"
            )
        ),
    }


# ============================================================
# MARKET
# ============================================================

def normalize_market(
    market_group,
    market,
    label_map,
    positional_templates,
    event_fixture_id,
):
    selections = market.get(
        "selections",
        [],
    )

    selection_count = len(
        selections
    )

    positional_labels = (
        positional_templates.get(
            selection_count
        )
    )

    normalized_selections = []

    for index, selection in enumerate(
        selections
    ):

        odds = (
            selection.get(
                "odds",
                {},
            )
            or {}
        )

        # ====================================================
        # IGNORA REGISTROS AUXILIARES SEM ODD
        # ====================================================

        if (
            odds.get(
                "fractional"
            )
            is None
        ):
            continue

        normalized = (
            normalize_selection(
                selection=selection,
                label_map=label_map,
                positional_labels=positional_labels,
                position=index,
                event_fixture_id=event_fixture_id,
            )
        )

        normalized_selections.append(
            normalized
        )

    if not normalized_selections:
        return None

    group_id = clean_text(
        market_group.get(
            "id"
        )
    )

    group_name = clean_text(
        market_group.get(
            "name"
        )
    )

    market_id = clean_text(
        market.get(
            "id"
        )
    )

    market_name = clean_text(
        market.get(
            "name"
        )
    )

    return {
        "group_id": group_id,

        # Útil posteriormente para banco,
        # pois alguns MG não possuem ID.
        "group_key": (
            group_id
            or market_id
            or group_name
        ),

        "group_name": group_name,

        "market_id": market_id,

        "market_name": market_name,

        "selections": (
            normalized_selections
        ),
    }


# ============================================================
# MARKET GROUP
# ============================================================

def normalize_market_group(
    market_group,
    event_fixture_id,
):
    group_name = clean_text(
        market_group.get(
            "name"
        )
    )

    # MEET e INFO não são mercados comerciais.
    if not group_name:
        return []

    label_map = (
        build_selection_label_map(
            market_group
        )
    )

    positional_templates = (
        build_positional_label_templates(
            market_group
        )
    )

    normalized_markets = []

    for market in market_group.get(
        "markets",
        [],
    ):

        normalized_market = (
            normalize_market(
                market_group=market_group,
                market=market,
                label_map=label_map,
                positional_templates=positional_templates,
                event_fixture_id=event_fixture_id,
            )
        )

        if normalized_market:
            normalized_markets.append(
                normalized_market
            )

    return normalized_markets


# ============================================================
# TIMES
# ============================================================

def extract_teams(
    market_groups,
):
    """
    Usa:

    Resultado Final

    time 1
    empate
    time 2
    """

    for market_group in market_groups:

        if (
            clean_text(
                market_group.get(
                    "name"
                )
            )
            != "Resultado Final"
        ):
            continue

        for market in market_group.get(
            "markets",
            [],
        ):

            selections = market.get(
                "selections",
                [],
            )

            names = []

            for selection in selections:

                odds = (
                    selection.get(
                        "odds",
                        {},
                    )
                    or {}
                )

                name = clean_text(
                    selection.get(
                        "name"
                    )
                )

                if (
                    name
                    and odds.get(
                        "fractional"
                    )
                    is not None
                ):
                    names.append(
                        name
                    )

            if len(names) < 3:
                continue

            if (
                names[1]
                .lower()
                == "empate"
            ):
                return {
                    "home": names[0],
                    "away": names[2],
                }

    return {
        "home": None,
        "away": None,
    }


# ============================================================
# MEETING
# ============================================================

def extract_meeting_id(
    parsed_data,
    event,
):
    pd_tokens = (
        parsed_data
        .get(
            "source",
            {},
        )
        .get(
            "pd_tokens",
            {},
        )
    )

    meeting_id = clean_text(
        pd_tokens.get(
            "E"
        )
    )

    if meeting_id:
        return meeting_id

    # ========================================================
    # FALLBACK:
    #
    # MEET139214757
    # ========================================================

    for group in event.get(
        "market_groups",
        [],
    ):

        group_id = clean_text(
            group.get(
                "id"
            )
        )

        if not group_id:
            continue

        match = re.match(
            r"^MEET(\d+)$",
            group_id,
        )

        if match:
            return match.group(1)

    return None


# ============================================================
# EVENT
# ============================================================

def normalize_event(
    parsed_data,
    competition,
    event,
):
    market_groups = (
        event.get(
            "market_groups",
            [],
        )
    )

    fixture_id = clean_text(
        event.get(
            "fixture_id"
        )
    )

    teams = extract_teams(
        market_groups
    )

    meeting_id = (
        extract_meeting_id(
            parsed_data,
            event,
        )
    )

    markets = []

    for market_group in market_groups:

        normalized_markets = (
            normalize_market_group(
                market_group=market_group,
                event_fixture_id=fixture_id,
            )
        )

        markets.extend(
            normalized_markets
        )

    # ========================================================
    # COUNTERS
    # ========================================================

    selection_count = sum(
        len(
            market.get(
                "selections",
                [],
            )
        )
        for market in markets
    )

    unnamed_selection_count = sum(
        1
        for market in markets
        for selection in market.get(
            "selections",
            [],
        )
        if not clean_text(
            selection.get(
                "name"
            )
        )
    )

    market_group_names = {
        market.get(
            "group_name"
        )
        for market in markets
        if market.get(
            "group_name"
        )
    }

    return {
        "competition_id": (
            competition.get(
                "id"
            )
        ),

        "competition_code": (
            competition.get(
                "code"
            )
        ),

        "meeting_id": meeting_id,

        "event_id": clean_text(
            event.get(
                "id"
            )
        ),

        "fixture_id": fixture_id,

        "start_time": (
            event.get(
                "start_time"
            )
        ),

        "schedule_raw": (
            event.get(
                "schedule_raw"
            )
        ),

        "streaming": (
            event.get(
                "streaming"
            )
        ),

        "home_team": (
            teams[
                "home"
            ]
        ),

        "away_team": (
            teams[
                "away"
            ]
        ),

        "market_group_count": len(
            market_group_names
        ),

        "market_count": len(
            markets
        ),

        "selection_count": (
            selection_count
        ),

        "unnamed_selection_count": (
            unnamed_selection_count
        ),

        "markets": markets,
    }


# ============================================================
# COUPON
# ============================================================

def normalize_coupon(
    parsed_data,
):
    events = []

    for competition in parsed_data.get(
        "competitions",
        [],
    ):

        for event in competition.get(
            "events",
            [],
        ):

            events.append(
                normalize_event(
                    parsed_data=parsed_data,
                    competition=competition,
                    event=event,
                )
            )

    source = parsed_data.get(
        "source",
        {},
    )

    return {
        "schema_version": 2,

        "source": {
            "sequence": (
                source.get(
                    "sequence"
                )
            ),

            "captured_at": (
                source.get(
                    "captured_at"
                )
            ),

            "pd": (
                source.get(
                    "pd"
                )
            ),

            "body_sha256": (
                source.get(
                    "body_sha256"
                )
            ),
        },

        "summary": {
            "event_count": len(
                events
            ),

            "market_count": sum(
                event[
                    "market_count"
                ]
                for event in events
            ),

            "selection_count": sum(
                event[
                    "selection_count"
                ]
                for event in events
            ),

            "unnamed_selection_count": sum(
                event[
                    "unnamed_selection_count"
                ]
                for event in events
            ),
        },

        "events": events,
    }


# ============================================================
# FILE
# ============================================================

def normalize_file(
    input_file: Path,
    output_file: Path,
):
    parsed_data = load_json(
        input_file
    )

    normalized = normalize_coupon(
        parsed_data
    )

    save_json(
        output_file,
        normalized,
    )

    print(
        "\n✓",
        input_file.name,
    )

    for event in normalized.get(
        "events",
        [],
    ):

        print(
            "  Fixture:",
            event[
                "fixture_id"
            ],
        )

        print(
            "  Meeting:",
            event[
                "meeting_id"
            ],
        )

        print(
            "  Partida:",
            event[
                "home_team"
            ],
            "x",
            event[
                "away_team"
            ],
        )

        print(
            "  Horário:",
            event[
                "start_time"
            ],
        )

        print(
            "  Grupos:",
            event[
                "market_group_count"
            ],
        )

        print(
            "  Mercados:",
            event[
                "market_count"
            ],
        )

        print(
            "  Seleções:",
            event[
                "selection_count"
            ],
        )

        print(
            "  Sem nome:",
            event[
                "unnamed_selection_count"
            ],
        )

    print(
        "  Output:",
        output_file,
    )


# ============================================================
# RUN
# ============================================================

def normalize_run(
    run_dir: Path,
):
    run_id = run_dir.name

    output_dir = (
        NORMALIZED_DIR
        / run_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

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

    for input_file in coupon_files:

        output_file = (
            output_dir
            / input_file.name
        )

        normalize_file(
            input_file=input_file,
            output_file=output_file,
        )

    print(
        "\n"
        + "=" * 80
    )

    print(
        "NORMALIZAÇÃO FINALIZADA"
    )

    print(
        "=" * 80
    )

    print(
        "Output:",
        output_dir,
    )


# ============================================================
# CLI
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Normalizer "
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

    # ========================================================
    # FILE
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
            input_file
            .parent
            .name
        )

        output_file = (
            NORMALIZED_DIR
            / run_id
            / input_file.name
        )

        normalize_file(
            input_file=input_file,
            output_file=output_file,
        )

        return

    # ========================================================
    # RUN
    # ========================================================

    if args.run:

        run_dir = Path(
            args.run
        )

        if not run_dir.exists():

            candidate = (
                PARSED_DIR
                / args.run
            )

            if candidate.exists():
                run_dir = candidate

            else:

                print(
                    "Run não encontrada:"
                )

                print(
                    args.run
                )

                return

    else:

        run_dir = find_latest_run(PARSED_DIR)

        if run_dir is None:

            print(
                "Nenhuma run encontrada em:"
            )

            print(
                PARSED_DIR
            )

            return

        print(
            "Usando última run:"
        )

        print(
            run_dir
        )

    normalize_run(
        run_dir
    )


# ============================================================
# ENTRYPOINT
# ============================================================

if __name__ == "__main__":
    main()
