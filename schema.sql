-- Fenrion Scout -- esquema de dados (multi-cliente desde o inicio)
--
-- Nome de trabalho "Fenrion Scout" -- muda-se facilmente, e so aparece em
-- comentarios e no README, nao esta hardcoded em nenhuma logica.
--
-- Filosofia: um stand pode ter varios "perfis de compra" em simultaneo
-- (ex: "SUVs ate 15k" e "carrinhas comerciais ate 10k" ao mesmo tempo).
-- Cada perfil e comparado contra as listagens normalizadas de leilao para
-- gerar "matches". As listagens sao normalizadas na entrada (cada adapter
-- de site converte o formato proprio do site para este esquema comum),
-- para o motor de matching e a apresentacao nunca precisarem de saber de
-- que site veio cada carro.

CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,              -- slug, ex: 'f2car'
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS wanted_profiles (
    id SERIAL PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    label TEXT NOT NULL,              -- ex: "SUVs ate 15k para revenda rapida"
    brand TEXT,                       -- null = qualquer marca
    model TEXT,                       -- null = qualquer modelo (match parcial, ver matching.py)
    year_min INT,
    year_max INT,
    km_max INT,
    price_min NUMERIC,
    price_max NUMERIC,
    engine_cc_min INT,                -- cilindrada
    engine_cc_max INT,
    fuels TEXT[] NOT NULL DEFAULT '{}',          -- vazio = qualquer
    gearbox TEXT,                     -- 'manual' | 'automatica' | null = qualquer
    condition_grades TEXT[] NOT NULL DEFAULT '{}', -- ex: {'sem_danos','danos_ligeiros'} -- vazio = qualquer
    countries TEXT[] NOT NULL DEFAULT '{}',       -- paises de leilao aceites -- vazio = qualquer
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS wanted_profiles_client_idx ON wanted_profiles (client_id) WHERE active;

-- Registo das fontes de leilao suportadas. Preenchido quando soubermos os
-- sites reais -- por agora fica vazio, e serve de "catalogo" para o painel
-- interno saber que adapters existem e o seu estado.
CREATE TABLE IF NOT EXISTS auction_sources (
    id TEXT PRIMARY KEY,              -- slug do site, ex: 'copart-eu'
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    country TEXT,
    requires_login BOOLEAN NOT NULL DEFAULT false,
    active BOOLEAN NOT NULL DEFAULT true,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Listagens normalizadas, uma linha por viatura em leilao (por fonte).
-- raw_data guarda o payload original do adapter, para nunca perdermos
-- informacao que ainda nao tenha campo proprio no esquema comum.
CREATE TABLE IF NOT EXISTS auction_listings (
    id SERIAL PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES auction_sources(id) ON DELETE CASCADE,
    external_id TEXT NOT NULL,        -- id do leilao no site de origem (para dedupe)
    brand TEXT,
    model TEXT,
    year INT,
    km INT,
    engine_cc INT,
    fuel TEXT,
    gearbox TEXT,
    condition_grade TEXT,
    price_current NUMERIC,
    currency TEXT NOT NULL DEFAULT 'EUR',
    auction_end_at TIMESTAMPTZ,
    listing_url TEXT NOT NULL,
    photo_url TEXT,
    country TEXT,
    raw_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, external_id)
);

CREATE INDEX IF NOT EXISTS auction_listings_active_idx ON auction_listings (auction_end_at);
CREATE INDEX IF NOT EXISTS auction_listings_brand_model_idx ON auction_listings (brand, model);

-- Correspondencias calculadas entre um perfil de compra e uma listagem.
-- Guardado (em vez de calculado sempre on-the-fly) para: (1) nao recalcular
-- tudo em cada pedido do dashboard, (2) suportar notificacoes "so avisar
-- uma vez por match novo" via a coluna notified.
CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    wanted_profile_id INT NOT NULL REFERENCES wanted_profiles(id) ON DELETE CASCADE,
    listing_id INT NOT NULL REFERENCES auction_listings(id) ON DELETE CASCADE,
    score INT,                        -- 0-100, grau de correspondencia (ver matching.py)
    notified BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (wanted_profile_id, listing_id)
);

CREATE INDEX IF NOT EXISTS matches_client_idx ON matches (client_id, created_at DESC);
