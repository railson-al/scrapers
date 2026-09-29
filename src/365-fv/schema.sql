-- ============================================================
-- SCHEMA SQLITE - BET365 VIRTUAL FOOTBALL
-- ============================================================
--
-- Aplicado por database.connect(); tudo é idempotente
-- (IF NOT EXISTS), então pode rodar a cada conexão.
--
-- Hierarquia: leagues -> games -> markets -> selections
--
-- Obs.: no protocolo o market_id identifica o GRUPO de mercado.
-- Um grupo como "Gols Mais/Menos" gera vários markets
-- ("Mais de", "Menos de") com o mesmo market_id, por isso
-- markets usa uma chave surrogate + posição dentro do jogo.


-- ============================================================
-- LIGAS
-- ============================================================

CREATE TABLE IF NOT EXISTS leagues (
    league_id   TEXT PRIMARY KEY,
    name        TEXT
);


-- ============================================================
-- JOGOS
-- ============================================================

CREATE TABLE IF NOT EXISTS games (
    fixture_id   TEXT PRIMARY KEY,
    league_id    TEXT REFERENCES leagues(league_id),
    meeting_id   TEXT,
    home_team    TEXT NOT NULL,
    away_team    TEXT NOT NULL,

    -- ISO local, sem timezone (como vem no campo CM)
    start_time   TEXT NOT NULL,

    -- NULL até existir um coletor de resultados
    home_score   INTEGER,
    away_score   INTEGER,

    -- última run que atualizou o jogo
    run_id       TEXT NOT NULL,
    captured_at  TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_start
    ON games(start_time);

CREATE INDEX IF NOT EXISTS idx_games_league
    ON games(league_id);


-- ============================================================
-- MERCADOS
-- ============================================================

CREATE TABLE IF NOT EXISTS markets (
    id           INTEGER PRIMARY KEY,
    fixture_id   TEXT NOT NULL
        REFERENCES games(fixture_id) ON DELETE CASCADE,

    -- ordem do mercado dentro do jogo (como no coupon)
    position     INTEGER NOT NULL,

    market_id    TEXT,
    group_id     TEXT,
    group_key    TEXT,
    group_name   TEXT,
    market_name  TEXT,

    UNIQUE (fixture_id, position)
);

CREATE INDEX IF NOT EXISTS idx_markets_group
    ON markets(group_name);


-- ============================================================
-- SELEÇÕES / ODDS
-- ============================================================

CREATE TABLE IF NOT EXISTS selections (
    market_pk        INTEGER NOT NULL
        REFERENCES markets(id) ON DELETE CASCADE,
    position         INTEGER NOT NULL,

    selection_id     TEXT NOT NULL,
    name             TEXT,
    label            TEXT,
    handicap         TEXT,
    odds_fractional  TEXT,
    odds_decimal     REAL,
    suspended        INTEGER,

    PRIMARY KEY (market_pk, selection_id)
);


-- ============================================================
-- VIEWS
-- ============================================================

CREATE VIEW IF NOT EXISTS games_view AS
SELECT
    g.fixture_id,
    g.home_team || ' x ' || g.away_team AS confronto,
    g.league_id,
    l.name AS liga,
    date(g.start_time) AS data,
    time(g.start_time) AS hora,
    g.home_score,
    g.away_score,
    CASE
        WHEN g.home_score IS NULL THEN NULL
        ELSE g.home_score || '-' || g.away_score
    END AS placar,
    g.start_time,
    g.run_id
FROM games g
LEFT JOIN leagues l
    ON l.league_id = g.league_id;

CREATE VIEW IF NOT EXISTS odds_view AS
SELECT
    g.fixture_id,
    g.home_team || ' x ' || g.away_team AS confronto,
    l.name AS liga,
    g.start_time,
    m.group_name,
    m.market_name,
    s.name AS selection,
    s.label,
    s.handicap,
    s.odds_fractional,
    s.odds_decimal,
    s.suspended
FROM selections s
JOIN markets m
    ON m.id = s.market_pk
JOIN games g
    ON g.fixture_id = m.fixture_id
LEFT JOIN leagues l
    ON l.league_id = g.league_id
ORDER BY
    g.start_time,
    g.fixture_id,
    m.position,
    s.position;
