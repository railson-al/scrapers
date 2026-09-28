# scrapers

Coleta de dados de **Futebol Virtual da Bet365** (`bet365.bet.br`) por engenharia reversa do tráfego de rede do site.

O navegador ([Camoufox](https://camoufox.com/), um Firefox anti-detecção controlado via Playwright) navega até *Esportes Virtuais → Futebol*. As respostas da `virtualsportscontentapi` são interceptadas e salvas cruas. Depois, duas etapas offline transformam o protocolo proprietário da Bet365 em JSON estruturado: eventos, mercados, seleções e odds.

> Projeto em fase de engenharia reversa. O significado de vários campos do protocolo ainda não foi confirmado. Por isso o parser **não descarta nada**: registros desconhecidos ficam guardados em `unknown_records`.

## Pipeline

```
 bet365.bet.br
      │  (Camoufox + interceptação de rede)
      ▼
 collector.py   ──►  data/raw/<run_id>/NNNN_{splash,coupon}.json + run.json
      │
      ▼
 parser.py      ──►  data/parsed/<run_id>/NNNN_coupon.json      (schema v1)
      │
      ▼
 normalizer.py  ──►  data/normalized/<run_id>/NNNN_coupon.json  (schema v2)
```

`<run_id>` é o timestamp da execução (`YYYYMMDD_HHMMSS`).

## Estrutura

```
.
├── pyproject.toml          # dependências (uv)
├── src/
│   ├── 365-fv/             # scraper Bet365 Futebol Virtual
│   │   ├── collector.py    # 1. coleta bruta via navegador (uma liga)
│   │   ├── collector_all.py # 1. coleta bruta de todas as ligas
│   │   ├── parser.py       # 2. tokeniza o protocolo e monta a hierarquia
│   │   ├── normalizer.py   # 3. achata para eventos → mercados → seleções
│   │   ├── test_leagues.py # diagnóstico: percorre as ligas e registra o tráfego
│   │   └── test_times.py   # diagnóstico: percorre os horários e registra o tráfego
│   └── scrapers/           # pacote do entrypoint `scrapers` (ainda placeholder)
└── data/                   # saídas (ignorado pelo git)
```

## Requisitos

- Python **3.13+**
- [uv](https://docs.astral.sh/uv/)
- Ambiente gráfico: o navegador roda com `headless=False`

## Instalação

```bash
uv sync
uv run camoufox fetch   # baixa o binário do navegador Camoufox
```

## Uso

Rode todos os comandos a partir da **raiz do repositório**, porque os scripts gravam em `data/` usando caminho relativo. O diretório `365-fv` tem hífen e não pode ser importado como pacote, então os scripts são executados direto pelo caminho.

### 1. Coleta

```bash
uv run python src/365-fv/collector.py                     # liga ativa por padrão
uv run python src/365-fv/collector.py --league "Euro Cup"  # trecho do nome
uv run python src/365-fv/collector.py --league 7           # posição [N] na lista impressa
uv run python src/365-fv/collector_all.py                  # todas as ligas, uma após a outra (~3 min)
```

1. Abre `https://www.bet365.bet.br/` e procura o item **Esportes Virtuais**.
2. Clica nele e espera o splash `#AVR#B144#` (Esportes Virtuais).
3. Testa candidatos de clique para **Futebol** até disparar o splash `#AVR#B146` (Futebol Virtual).
4. Lista os cards de liga (`div.vcm-d4`, o ativo tem `vcm-98c`) e seleciona a liga de `--league` (o `collector_all.py` percorre todas). Existem ligas com o mesmo nome (variantes com IDs `C` diferentes); nesse caso use o número `[N]`. As variantes `VR_NJ_*` do splash (hoje as posições 2, 3 e 7) têm horários no fuso dos EUA e sempre retornam coupons vazios no .bet.br.
5. Descobre os horários da faixa ao lado de "Resultados" e clica em cada um, esperando o coupon daquele jogo antes do próximo clique. Cada coupon traz **um único jogo**, identificado pelo `E<ChallengeID>` do `pd`. O horário já exibido não dispara request; nele é usado o último coupon capturado.

Cada arquivo bruto contém a URL, os parâmetros de query (incluindo `pd`) e os headers relevantes. Os cookies ficam só como nomes e hash SHA-256. O corpo da resposta é salvo inteiro, com tamanho e SHA-256. O `run.json` registra o início e o fim da execução, as ligas disponíveis, a liga coletada (`league`, `league_position`, `league_id`) e seus `time_slots`: horário, `league_id`/`challenge_id`, arquivo e `start_matches` (o início do jogo no `CM` do coupon bate com o horário clicado). No `collector_all.py`, isso fica numa lista `leagues`, com um item por liga (`position`, `name`, `league_id`, `time_slots`). A lista `coupons` resume todos os coupons salvos:

- `empty: true`: sem mercados (corpo vazio ou `EV;ID=EMB;`). Acontece nas ligas `VR_NJ_*`, quando o site suspende as apostas ou no jogo mais distante, ainda não publicado.
- `stale: true`: coupon de transição. Ao trocar de liga, o frontend pede a liga nova (`C`) com o jogo da liga anterior (`E`), e o servidor responde pelo `E`, ou seja, com um jogo de **outra** liga. Esses coupons também ficam `linked: false` (sem horário) e devem ser ignorados para não duplicar eventos.

### 2. Parser

```bash
uv run python src/365-fv/parser.py                    # última execução em data/raw/
uv run python src/365-fv/parser.py --run 20260927_113032
uv run python src/365-fv/parser.py --file data/raw/20260927_113032/0003_coupon.json
```

Processa apenas arquivos `*_coupon.json`. Etapas:

- **Tokenização:** o corpo (`F|CL;...|EV;...|MG;...|MA;...|PA;...|`) vira uma lista de registros `{type, fields}`.
- **Hierarquia:** `CL` (competição) → `EV` (evento) → `MG` (grupo de mercado) → `MA` (mercado) → `PA` (seleção).
- **Odds:** convertidas de fracionária para decimal (`11/8 → 2.375`), mantendo a original.
- **Horário:** extraído do campo `CM` (`Lista da Partida~20260926191900 → 2026-09-26T19:19:00`), sem timezone.
- **`pd`:** decomposto em tokens (`#AC#B146#C…#D1#E…#F2#`).

A saída inclui `summary`, `competitions`, `unknown_records` e todos os `records` tokenizados, para inspeção.

### 3. Normalizer

```bash
uv run python src/365-fv/normalizer.py                # última execução em data/parsed/
uv run python src/365-fv/normalizer.py --run 20260927_113032
uv run python src/365-fv/normalizer.py --file data/parsed/20260927_113032/0003_coupon.json
```

Gera uma estrutura plana e pronta para banco de dados:

- Extrai mandante/visitante (`home_team`, `away_team`) e `meeting_id`.
- Resolve nomes e labels das seleções pelo ID. Nos grupos em que o label depende da posição (`Gols Mais/Menos`, `Resultado/Ambos Marcam`, `Margem de Vitória`, entre outros), usa os templates de posição definidos em `POSITIONAL_LABEL_GROUPS`.
- Extrai o handicap e descarta registros auxiliares sem odd.
- Cria uma `group_key` estável para grupos de mercado sem ID.

Exemplo (resumido):

```json
{
  "schema_version": 2,
  "summary": { "event_count": 1, "market_count": 36, "selection_count": 273 },
  "events": [{
    "competition_id": "146",
    "event_id": "E201973451",
    "fixture_id": "201973451",
    "start_time": "2026-09-27T15:31:00",
    "home_team": "Austrália",
    "away_team": "Uruguai",
    "markets": [{
      "group_name": "Resultado Final",
      "market_id": "B1-21460031",
      "selections": [{
        "id": "92845883",
        "name": "Austrália",
        "odds_fractional": "15/8",
        "odds_decimal": 2.875,
        "suspended": "0"
      }]
    }]
  }]
}
```

### Scripts de diagnóstico

Servem para mapear a navegação e as requisições de rede. Os dois abrem o navegador, chegam em Futebol Virtual, clicam em cada item e registram as requisições e respostas disparadas por cada clique.

```bash
uv run python src/365-fv/test_leagues.py   # clica em cada liga
uv run python src/365-fv/test_times.py     # clica em cada horário da liga ativa (e na área de Resultados)
```

Os resultados vão para `data/diagnostics/<run_id>/` (`leagues.json` e `times.json`, respectivamente).

## Limitações conhecidas

- A semântica de vários tokens (`pd`, campos de `EV`/`MA`/`PA`) ainda não foi confirmada.
- `start_time` não tem timezone definido.
- A coleta pega uma liga por execução, sem agendamento nem loop contínuo.
- Os seletores de DOM são heurísticos (pontuação de candidatos) e podem quebrar se o layout do site mudar.
- O entrypoint `scrapers` (`src/scrapers`) ainda é um placeholder. `python-dotenv` está nas dependências, mas ainda não é usado.
