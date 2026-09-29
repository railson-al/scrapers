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
      │
      ▼
 loader.py      ──►  data/db/bet365.sqlite                     (SQLite)
      │
      ▼
 dashboard.py   ──►  Streamlit (grid de jogos + detalhes)
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
│   │   ├── loader.py       # 4. grava o normalized no SQLite
│   │   ├── schema.sql      # schema do banco (leagues, games, markets, selections + views)
│   │   ├── database.py     # conexão SQLite e upserts, compartilhado
│   │   ├── dashboard.py    # 5. dashboard Streamlit sobre o SQLite
│   │   ├── dashboard_queries.py # consultas de leitura do dashboard
│   │   ├── config.py       # constantes compartilhadas (URL, diretórios de data/)
│   │   ├── utils.py        # helpers puros compartilhados (datas, pd, JSON, URLs)
│   │   ├── navigation.py   # RawCollector + navegação no site, usados pelos coletores
│   │   └── tests/
│   │       ├── test_leagues.py # diagnóstico: percorre as ligas e registra o tráfego
│   │       └── test_times.py   # diagnóstico: percorre os horários e registra o tráfego
├── tests/                  # testes pytest (uv run pytest)
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

Rode todos os comandos a partir da **raiz do repositório**, porque os scripts gravam em `data/` usando caminho relativo. O diretório `365-fv` tem hífen e não pode ser importado como pacote, então os scripts são executados direto pelo caminho e importam `config`, `utils` e `navigation` como módulos soltos da mesma pasta (os scripts em `tests/` adicionam a pasta pai ao `sys.path`).

### 1. Coleta

```bash
uv run python src/365-fv/collector.py                     # liga ativa por padrão
uv run python src/365-fv/collector.py --league "Euro Cup"  # trecho do nome
uv run python src/365-fv/collector.py --league 7           # posição [N] na lista impressa
uv run python src/365-fv/collector_all.py                  # todas as ligas, uma após a outra (~3 min)
uv run python src/365-fv/collector.py --no-results         # pula a aba Resultados (vale para os dois)
uv run python src/365-fv/collector.py --league 1 --watch 60 --click-delay 300  # sessão contínua, ver abaixo
```

1. Abre `https://www.bet365.bet.br/` e procura o item **Esportes Virtuais**.
2. Clica nele e espera o splash `#AVR#B144#` (Esportes Virtuais).
3. Testa candidatos de clique para **Futebol** até disparar o splash `#AVR#B146` (Futebol Virtual).
4. Lista os cards de liga (`div.vcm-d4`, o ativo tem `vcm-98c`) e seleciona a liga de `--league` (o `collector_all.py` percorre todas). Existem ligas com o mesmo nome (variantes com IDs `C` diferentes); nesse caso use o número `[N]`. As variantes `VR_NJ_*` do splash (hoje as posições 2, 3 e 7) têm horários no fuso dos EUA e sempre retornam coupons vazios no .bet.br.
5. Descobre os horários da faixa ao lado de "Resultados" e clica em cada um, esperando o coupon daquele jogo antes do próximo clique. Cada coupon traz **um único jogo**, identificado pelo `E<ChallengeID>` do `pd`. O horário já exibido não dispara request; nele é usado o último coupon capturado.
6. Clica na aba **Resultados** da liga (a menos que se passe `--no-results`). Ela chama `contentdata/virtualsportscontentapi/results` com `pd=#AVA#B146#C<league_id>#R^1#`, salvo como `NNNN_results.json`. Para diagnóstico, a etapa também grava XHRs do site fora da API (`NNNN_results_xhr.json`) e um snapshot do texto/HTML da tela (`NNNN_results_dom.json`). O resumo fica em `results` no `run.json` (em `leagues[]` no `collector_all.py`). Uma falha nessa etapa é registrada em `results.error` e não interrompe a coleta.

**Ordem e modo contínuo (`collector.py`).** Os resultados são lidos **antes** dos horários, porque a aba mostra só 2 jogos por vez e a janela é curta. Com `--watch SEGUNDOS`, o navegador fica aberto na liga e o ciclo (Resultados + todos os horários) se repete a cada N segundos, sem refazer a navegação. Cada ciclo é uma run própria em `data/raw/`, já processada por parser → normalizer → loader, e imprime uma linha `[pipeline]` de resumo. `--click-delay MS` ajusta a espera entre os cliques nos horários (padrão: 1000). `--cycles N` limita o número de ciclos. Três ciclos seguidos sem nenhum coupon encerram o modo. A cada falha, a navegação é refeita a partir da home. A entrada em Esportes Virtuais aceita o menu lateral quando o bloco principal não aparece, e o bloco de futebol é aceito como "Futebol" ou "Football".

Cada arquivo bruto contém a URL, os parâmetros de query (incluindo `pd`) e os headers relevantes. Os cookies ficam só como nomes e hash SHA-256. O corpo da resposta é salvo inteiro, com tamanho e SHA-256. O `run.json` registra o início e o fim da execução, as ligas disponíveis, a liga coletada (`league`, `league_position`, `league_id`) e seus `time_slots`: horário, `league_id`/`challenge_id`, arquivo e `start_matches` (o início do jogo no `CM` do coupon bate com o horário clicado). No `collector_all.py`, isso fica numa lista `leagues`, com um item por liga (`position`, `name`, `league_id`, `time_slots`). A lista `coupons` resume todos os coupons salvos:

- `empty: true`: sem mercados (corpo vazio ou `EV;ID=EMB;`). Acontece nas ligas `VR_NJ_*`, quando o site suspende as apostas ou no jogo mais distante, ainda não publicado.
- `stale: true`: coupon de transição. Ao trocar de liga, o frontend pede a liga nova (`C`) com o jogo da liga anterior (`E`), e o servidor responde pelo `E`, ou seja, com um jogo de **outra** liga. Esses coupons também ficam `linked: false` (sem horário) e devem ser ignorados para não duplicar eventos.

### 2. Parser

```bash
uv run python src/365-fv/parser.py                    # última execução em data/raw/
uv run python src/365-fv/parser.py --run 20260927_113032
uv run python src/365-fv/parser.py --file data/raw/20260927_113032/0003_coupon.json
```

Processa os arquivos `*_coupon.json` e `*_results.json`. Nos resultados, cada jogo encerrado é um `MG` com `N2`/`N3` (mandante/visitante), `SS` (placar `casa#fora`), `SM` (horário `H.MM`) e `NA` (liga), seguido dos `PA` com as seleções vencedoras. Eles saem em `results`, cada um com seus `fields`, `market` e `selections`. Nos coupons, as etapas são:

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
- Nos `*_results.json`, gera um item por jogo: `league_id` (do `C` do `pd`), `result_time` (`SM` → `HH:MM`), times, `home_score`/`away_score` (NULL quando o `SS` vem vazio, `#`), placar do intervalo (de "Resultado Correto - Intervalo") e `winner` (`home`/`draw`/`away`, de "Resultado Final").

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

### 4. Loader (SQLite)

```bash
uv run python src/365-fv/loader.py                    # última execução em data/normalized/
uv run python src/365-fv/loader.py --run 20260927_113032
uv run python src/365-fv/loader.py --file data/normalized/20260927_113032/0003_coupon.json
```

Grava em `data/db/bet365.sqlite`, usando o schema de `src/365-fv/schema.sql` (aplicado automaticamente a cada conexão):

- `leagues` (`league_id`, `name`): o nome vem do `run.json` da captura crua, casado pelo nome do arquivo. Sem ele, o id sai do código `M` do `pd`.
- `games`: um jogo por `fixture_id`, com mandante/visitante, `league_id`, `start_time`, `home_score`/`away_score` (preenchidos pelos resultados, ver abaixo) e a última `run_id`.
- `markets`: mercados do jogo, identificados por `(fixture_id, position)`. O `market_id` do protocolo identifica o grupo e se repete entre colunas como "Mais de"/"Menos de".
- `selections`: seleções com `odds_fractional` e `odds_decimal`.
- `results`: resultados da aba Resultados, inclusive os que ainda não casaram com um jogo (`fixture_id` NULL).
- Views `games_view` (confronto, liga, data, hora, placar) e `odds_view` (odds achatadas com o jogo).

**Resultados e placares.** O results não traz `fixture_id`, só `HH:MM`. A data é inferida pelo horário de referência da liga na mesma run (o menor `start_time` dos coupons dela): o jogo é o último `HH:MM` até essa referência, ou seja, o do dia anterior quando passa da meia-noite. Se existir o jogo do coupon com a mesma liga, os mesmos times e o mesmo `start_time` **exato**, o placar vai para ele. Senão, o resultado **cria o próprio jogo** em `games`, com `fixture_id` sintético (`res:<liga>|<início>|<mandante>|<visitante>`) e sem odds. Se o coupon real chegar depois, o resultado passa para ele e o jogo sintético é apagado. Isso roda a cada carga. Sem referência de data (liga sem nenhum coupon com dados na run), o resultado fica só na tabela `results`.

A carga é idempotente: recarregar uma run atualiza o jogo e troca as odds pelo snapshot mais recente, sem apagar o placar.

```bash
sqlite3 data/db/bet365.sqlite "SELECT confronto, liga, data, hora, placar FROM games_view LIMIT 5;"
```

### 5. Dashboard (Streamlit)

```bash
uv run streamlit run src/365-fv/dashboard.py
```

Lê `data/db/bet365.sqlite` em modo somente leitura (rode o loader antes). A barra lateral filtra por liga (pelo nome, porque a mesma liga aparece com mais de um `league_id`). O grid lista os jogos do mais recente para o mais antigo, e selecionar uma linha mostra os detalhes do jogo e as odds agrupadas por grupo de mercado, na ordem do coupon.

### Testes

```bash
uv run pytest
```

Os testes ficam em `tests/` na raiz e usam um SQLite temporário. Os `test_*.py` de `src/365-fv/tests/` não são testes pytest (veja abaixo).

### Scripts de diagnóstico

Servem para mapear a navegação e as requisições de rede. Os dois abrem o navegador, chegam em Futebol Virtual, clicam em cada item e registram as requisições e respostas disparadas por cada clique.

```bash
uv run python src/365-fv/tests/test_leagues.py   # clica em cada liga
uv run python src/365-fv/tests/test_times.py     # clica em cada horário da liga ativa
```

Os resultados vão para `data/diagnostics/<run_id>/` (`leagues.json` e `times.json`, respectivamente).

## Limitações conhecidas

- A semântica de vários tokens (`pd`, campos de `EV`/`MA`/`PA`) ainda não foi confirmada.
- `start_time` não tem timezone definido.
- A aba Resultados mostra só 2 jogos por liga, de um cache do servidor que avança aos saltos e fica de minutos a ~2h30 atrás da faixa de horários (varia por liga). Os jogos entre um par e outro nunca aparecem.
- Muitas sessões novas em pouco tempo fazem o site devolver coupons vazios (HTTP 200 sem corpo). Prefira `--watch`, que abre a página uma vez só.
- A coleta pega uma liga por execução, sem agendamento nem loop contínuo.
- Os seletores de DOM são heurísticos (pontuação de candidatos) e podem quebrar se o layout do site mudar.
- `python-dotenv` está nas dependências, mas ainda não é usado.
