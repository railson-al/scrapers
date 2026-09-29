# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A reverse-engineering scraper for **Bet365 Virtual Football** (`bet365.bet.br`). A Camoufox browser (anti-detection Firefox driven via Playwright) navigates the site, intercepts `virtualsportscontentapi` responses, and saves them raw; two offline stages then decode Bet365's proprietary text protocol into structured JSON. The README (in Portuguese) documents the pipeline and each stage in detail — read it before larger changes.

## Commands

Always run from the **repository root**: every script writes to `data/` via a relative path (`Path("data")`).

```bash
uv sync
uv run camoufox fetch                          # one-time: download the Camoufox browser binary

uv run python src/365-fv/collector.py [--league <name|N>]  # 1. collect every game of one league -> data/raw/<run_id>/
uv run python src/365-fv/collector_all.py                  # 1. (alt) every game of every league, same output format
uv run python src/365-fv/parser.py             # 2. raw -> data/parsed/<run_id>/     (schema v1)
uv run python src/365-fv/normalizer.py         # 3. parsed -> data/normalized/<run_id>/ (schema v2)
uv run python src/365-fv/loader.py             # 4. normalized -> data/db/bet365.sqlite (SQLite)
uv run streamlit run src/365-fv/dashboard.py   # 5. dashboard (grid de jogos por liga + detalhes), lê o SQLite read-only
uv run pytest                                  # testes em tests/ (raiz)
```

`parser.py`, `normalizer.py` and `loader.py` default to the latest run and accept `--run <run_id>` or `--file <path>` to process one run or a single file — use `--file` for fast iteration against an existing capture. `<run_id>` is `YYYYMMDD_HHMMSS`.

pytest runs only the root `tests/` (configured via `[tool.pytest.ini_options]` in `pyproject.toml`, with `src/365-fv` on `pythonpath`); no linter or formatter is configured. `src/365-fv/tests/test_leagues.py` and `src/365-fv/tests/test_times.py` are **not pytest tests**: they are browser-driven diagnostic scripts that click each league / each time slot and log the network traffic each click triggers, writing to `data/diagnostics/<run_id>/`. Run them like the other scripts.

Anything that opens the browser (`collector*.py`, `test_*.py`) runs with `headless=False` and needs a graphical environment plus live access to the site — you generally cannot run these yourself; the parser/normalizer can be run offline against existing `data/` captures.

## Architecture

- `src/365-fv/` is a directory of **standalone scripts**, not an importable package (the hyphen in the name prevents imports). Shared code lives in sibling modules imported by plain name (`python src/365-fv/x.py` puts that folder on `sys.path`): `config.py` (constants: `BASE_URL`, `RAW_DIR`, `PARSED_DIR`, ...), `utils.py` (pure helpers: `now_iso`, `parse_pd`, `load_json`/`save_json`, `find_latest_run(base_dir)`, `classify_url`, ...) and `navigation.py` (`RawCollector` plus all browser navigation used by both collectors). Scripts in `tests/` insert the parent folder into `sys.path` before importing these. Put new shared code there instead of copying it.
- The diagnostic scripts in `tests/` still keep their own variants of some navigation functions and `NetworkMonitor` (they differ from the collectors' versions on purpose).
- The stages communicate only through JSON files in `data/` (git-ignored). Each stage's output schema is the next stage's input contract: collector writes `NNNN_{splash,coupon}.json` + `run.json`; parser only consumes `*_coupon.json`; normalizer consumes parser output. Changing a field name in one stage means updating the consumer.
- **Protocol:** coupon bodies look like `F|CL;...|EV;...|MG;...|MA;...|PA;...|`. The parser tokenizes these into `{type, fields}` records and builds the hierarchy `CL` (competition) → `EV` (event) → `MG` (market group) → `MA` (market) → `PA` (selection). Odds are fractional and converted to decimal while keeping the original; start time comes from the `CM` field and has no timezone.
- **Never drop unknown data in the parser.** Many protocol fields are still unconfirmed, so unrecognized records go to `unknown_records` and all tokenized `records` are kept in the output for inspection. The normalizer is where data is flattened and auxiliary odds-less records are discarded.
- In the normalizer, some market groups label selections by position rather than by ID; these are listed in `POSITIONAL_LABEL_GROUPS` (matched by exact Portuguese group name). Groups without an ID get a synthetic stable `group_key`.
- **Navigation:** the collector confirms progress via splash `pd` codes — `#AVR#B144#` = Virtual Sports, `B146` = Virtual Football. DOM targets are found by heuristic candidate scoring (`score_ancestor` / `ancestor_locator` in `collector.py`), not fixed selectors, and are fragile to layout changes.
- **Database:** `schema.sql` (DDL, applied on every `database.connect()`) + `database.py` (upserts). Tables `leagues` → `games` (PK `fixture_id`) → `markets` (surrogate `id`, unique `(fixture_id, position)` — the protocol `market_id` is per *group* and repeats across columns like Mais de/Menos de) → `selections`. League name comes from the raw `run.json` (matched by coupon file name), not from the normalized output. `upsert_game` never touches `home_score`/`away_score` (NULL until a results collector exists; use `set_score`). Loading is idempotent: markets/selections are replaced by the latest snapshot.
- Raw captures store cookies only as names + SHA-256 hashes; keep it that way.
- **Dashboard:** `dashboard.py` (Streamlit UI) + `dashboard_queries.py` (pure read queries, tested). It opens the DB read-only (`mode=ro`) instead of `database.connect()`, which runs DDL. Leagues are filtered by *name*, since one name maps to several `league_id`s.
- `[tool.uv] package = false`: the repo is scripts only (`src/scrapers/` and its `scrapers` entrypoint were removed); `python-dotenv` is a dependency but unused.

## Conventions

- Code comments, log output, and the README are in Portuguese; follow that in this repo.
- Python 3.13+, managed with `uv`.
