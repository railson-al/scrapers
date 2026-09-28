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
```

`parser.py` and `normalizer.py` default to the latest run and accept `--run <run_id>` or `--file <path>` to process one run or a single file — use `--file` for fast iteration against an existing capture. `<run_id>` is `YYYYMMDD_HHMMSS`.

There is no test suite, linter, or formatter configured. `test_leagues.py` and `test_times.py` are **not pytest tests**: they are browser-driven diagnostic scripts that click each league / each time slot and log the network traffic each click triggers, writing to `data/diagnostics/<run_id>/`. Run them like the other scripts.

Anything that opens the browser (`collector*.py`, `test_*.py`) runs with `headless=False` and needs a graphical environment plus live access to the site — you generally cannot run these yourself; the parser/normalizer can be run offline against existing `data/` captures.

## Architecture

- `src/365-fv/` is a directory of **standalone scripts**, not an importable package (the hyphen in the name prevents imports). Helpers such as `parse_url_query`, `parse_pd`, `now_iso`, `classify_url` and the `NetworkMonitor` class are duplicated across files rather than shared. When changing one of these, check the other scripts for their copy.
- The stages communicate only through JSON files in `data/` (git-ignored). Each stage's output schema is the next stage's input contract: collector writes `NNNN_{splash,coupon}.json` + `run.json`; parser only consumes `*_coupon.json`; normalizer consumes parser output. Changing a field name in one stage means updating the consumer.
- **Protocol:** coupon bodies look like `F|CL;...|EV;...|MG;...|MA;...|PA;...|`. The parser tokenizes these into `{type, fields}` records and builds the hierarchy `CL` (competition) → `EV` (event) → `MG` (market group) → `MA` (market) → `PA` (selection). Odds are fractional and converted to decimal while keeping the original; start time comes from the `CM` field and has no timezone.
- **Never drop unknown data in the parser.** Many protocol fields are still unconfirmed, so unrecognized records go to `unknown_records` and all tokenized `records` are kept in the output for inspection. The normalizer is where data is flattened and auxiliary odds-less records are discarded.
- In the normalizer, some market groups label selections by position rather than by ID; these are listed in `POSITIONAL_LABEL_GROUPS` (matched by exact Portuguese group name). Groups without an ID get a synthetic stable `group_key`.
- **Navigation:** the collector confirms progress via splash `pd` codes — `#AVR#B144#` = Virtual Sports, `B146` = Virtual Football. DOM targets are found by heuristic candidate scoring (`score_ancestor` / `ancestor_locator` in `collector.py`), not fixed selectors, and are fragile to layout changes.
- Raw captures store cookies only as names + SHA-256 hashes; keep it that way.
- `src/scrapers/` (the `scrapers` entrypoint in `pyproject.toml`) is still a placeholder; `python-dotenv` is a dependency but unused.

## Conventions

- Code comments, log output, and the README are in Portuguese; follow that in this repo.
- Python 3.13+, managed with `uv`.
