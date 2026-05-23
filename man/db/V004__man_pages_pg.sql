-- V004__man_pages_pg.sql — PostgreSQL migration target for man page pipeline
-- Run after migrating V001–V003 SQLite tables to PostgreSQL.
-- Uses TEXT[] for arrays and TIMESTAMP WITH TIME ZONE for timestamps.

CREATE TABLE IF NOT EXISTS flc_assets (
  flc_code      TEXT        NOT NULL PRIMARY KEY,
  label         TEXT        NOT NULL,
  description   TEXT,
  asset_type    TEXT        NOT NULL,
  collibra_id   TEXT,
  dw_system     TEXT        NOT NULL DEFAULT 'singine',
  mandate_start DATE        NOT NULL,
  mandate_end   DATE        NOT NULL,
  contract_id   TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dw_dimensions (
  gen_id        TEXT        NOT NULL PRIMARY KEY,
  flc_code      TEXT        NOT NULL REFERENCES flc_assets(flc_code),
  dimension     TEXT        NOT NULL
                CHECK(dimension IN
                  ('main','primary','secondary','n_linear',
                   'relational','boolean','temporal')),
  axis          TEXT,
  dw_system     TEXT        NOT NULL DEFAULT 'singine',
  description   TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sidebar_entries (
  gen_id        TEXT        NOT NULL PRIMARY KEY,
  page_id       TEXT        NOT NULL,
  nav_label     TEXT        NOT NULL,
  nav_href      TEXT        NOT NULL,
  depth         INTEGER     NOT NULL DEFAULT 0,
  parent_id     TEXT        REFERENCES sidebar_entries(gen_id),
  title         TEXT,
  summary       TEXT,
  keywords      TEXT[],
  section_ids   TEXT[],
  silkpage_src  TEXT        NOT NULL,
  flc_code      TEXT        REFERENCES flc_assets(flc_code),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS man_pages (
  gen_id        TEXT        NOT NULL PRIMARY KEY,
  page_id       TEXT        NOT NULL UNIQUE,
  flc_code      TEXT        NOT NULL DEFAULT 'MANP' REFERENCES flc_assets(flc_code),
  sidebar_id    TEXT        REFERENCES sidebar_entries(gen_id),
  man_section   INTEGER     NOT NULL DEFAULT 1,
  title         TEXT        NOT NULL,
  synopsis      TEXT,
  description   TEXT,
  content_roff  TEXT        NOT NULL,
  db_source     TEXT        NOT NULL DEFAULT 'pg'
                CHECK(db_source IN ('sqlite','pg')),
  generated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  output_path   TEXT
);

CREATE TABLE IF NOT EXISTS data_citizens (
  citizen_id    TEXT        NOT NULL PRIMARY KEY,
  label         TEXT        NOT NULL,
  community     TEXT        NOT NULL DEFAULT 'sindoc',
  public_profile_url TEXT,
  email         TEXT,
  flc_mandate   TEXT[],
  active        BOOLEAN     NOT NULL DEFAULT TRUE,
  registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS man_page_citizens (
  gen_id        TEXT        NOT NULL PRIMARY KEY,
  man_page_id   TEXT        NOT NULL REFERENCES man_pages(gen_id),
  citizen_id    TEXT        NOT NULL REFERENCES data_citizens(citizen_id),
  role          TEXT        NOT NULL DEFAULT 'contributor'
                CHECK(role IN ('author','contributor','steward','reviewer')),
  linked_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS migration_services (
  gen_id            TEXT        NOT NULL PRIMARY KEY,
  service_name      TEXT        NOT NULL,
  from_tech         TEXT        NOT NULL DEFAULT 'mule'
                    CHECK(from_tech IN ('mule','camel','spring-integration','custom')),
  to_tech           TEXT        NOT NULL DEFAULT 'springboot'
                    CHECK(to_tech IN ('springboot','quarkus','micronaut','custom')),
  flc_code          TEXT        REFERENCES flc_assets(flc_code),
  status            TEXT        NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','in-progress','completed','deprecated')),
  man_page_id       TEXT        REFERENCES man_pages(gen_id),
  collibra_contract TEXT,
  endpoint_url      TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_sidebar_page_id  ON sidebar_entries(page_id);
CREATE INDEX IF NOT EXISTS idx_man_page_id      ON man_pages(page_id);
CREATE INDEX IF NOT EXISTS idx_man_flc          ON man_pages(flc_code);
CREATE INDEX IF NOT EXISTS idx_dw_flc           ON dw_dimensions(flc_code);
CREATE INDEX IF NOT EXISTS idx_migr_status      ON migration_services(status);
CREATE INDEX IF NOT EXISTS idx_citizen_community ON data_citizens(community);
