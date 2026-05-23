-- V004__man_pages.sql — Man page pipeline: FLC-governed, silkpage-sourced
-- SQLite dialect. Apply after V003__categories.sql.
-- Migrate to PostgreSQL via V004__man_pages_pg.sql.

-- ── Four Letter Code (FLC) asset manifest ────────────────────────────────────
-- FLCs are Collibra-governed 4-character codes from the 1-year mandate contract.
CREATE TABLE IF NOT EXISTS flc_assets (
  flc_code      TEXT NOT NULL PRIMARY KEY,          -- e.g. MANP
  label         TEXT NOT NULL,
  description   TEXT,
  asset_type    TEXT NOT NULL,                      -- Collibra asset type name
  collibra_id   TEXT,                               -- Collibra asset UUID if registered
  dw_system     TEXT NOT NULL DEFAULT 'singine',
  mandate_start TEXT NOT NULL,
  mandate_end   TEXT NOT NULL,
  contract_id   TEXT,                               -- c.contract.* reference
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ── Data warehouse dimension mapping ─────────────────────────────────────────
-- Maps each FLC to the DW dimensions it participates in (main/primary/secondary).
CREATE TABLE IF NOT EXISTS dw_dimensions (
  gen_id        TEXT NOT NULL PRIMARY KEY,
  flc_code      TEXT NOT NULL REFERENCES flc_assets(flc_code),
  dimension     TEXT NOT NULL
                     CHECK(dimension IN
                       ('main','primary','secondary','n_linear',
                        'relational','boolean','temporal')),
  axis          TEXT,                               -- time / subject / operation / data-citizen
  dw_system     TEXT NOT NULL DEFAULT 'singine',
  description   TEXT,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  UNIQUE(flc_code, dimension, axis)
);

-- ── Silkpage sidebar entries ──────────────────────────────────────────────────
-- One row per silkpage TOC/navigation entry (page metadata from <head>).
CREATE TABLE IF NOT EXISTS sidebar_entries (
  gen_id        TEXT NOT NULL PRIMARY KEY,
  page_id       TEXT NOT NULL,                      -- webpage/@id attribute
  nav_label     TEXT NOT NULL,
  nav_href      TEXT NOT NULL,
  depth         INTEGER NOT NULL DEFAULT 0,
  parent_id     TEXT REFERENCES sidebar_entries(gen_id),
  title         TEXT,
  summary       TEXT,
  keywords      TEXT,                               -- comma-separated
  section_ids   TEXT,                               -- JSON array of section/@id
  silkpage_src  TEXT NOT NULL,                      -- relative path to XML source
  flc_code      TEXT REFERENCES flc_assets(flc_code),
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ── Generated man page records ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS man_pages (
  gen_id        TEXT NOT NULL PRIMARY KEY,
  page_id       TEXT NOT NULL UNIQUE,              -- e.g. singine-cleanup-1
  flc_code      TEXT NOT NULL DEFAULT 'MANP' REFERENCES flc_assets(flc_code),
  sidebar_id    TEXT REFERENCES sidebar_entries(gen_id),
  man_section   INTEGER NOT NULL DEFAULT 1,
  title         TEXT NOT NULL,
  synopsis      TEXT,
  description   TEXT,
  content_roff  TEXT NOT NULL,
  db_source     TEXT NOT NULL DEFAULT 'sqlite'
                     CHECK(db_source IN ('sqlite','pg')),
  generated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  output_path   TEXT
);

-- ── Community-active data citizens ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS data_citizens (
  citizen_id    TEXT NOT NULL PRIMARY KEY,          -- public community ID
  label         TEXT NOT NULL,
  community     TEXT NOT NULL DEFAULT 'sindoc',
  public_profile_url TEXT,
  email         TEXT,
  flc_mandate   TEXT,                               -- CSV of FLC codes citizen is bound by
  active        INTEGER NOT NULL DEFAULT 1,
  registered_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ── Man page ↔ data citizen link ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS man_page_citizens (
  gen_id        TEXT NOT NULL PRIMARY KEY,
  man_page_id   TEXT NOT NULL REFERENCES man_pages(gen_id),
  citizen_id    TEXT NOT NULL REFERENCES data_citizens(citizen_id),
  role          TEXT NOT NULL DEFAULT 'contributor'
                     CHECK(role IN ('author','contributor','steward','reviewer')),
  linked_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ── Migration services (Mule → Spring Boot) ──────────────────────────────────
CREATE TABLE IF NOT EXISTS migration_services (
  gen_id            TEXT NOT NULL PRIMARY KEY,
  service_name      TEXT NOT NULL,
  from_tech         TEXT NOT NULL DEFAULT 'mule'
                         CHECK(from_tech IN ('mule','camel','spring-integration','custom')),
  to_tech           TEXT NOT NULL DEFAULT 'springboot'
                         CHECK(to_tech IN ('springboot','quarkus','micronaut','custom')),
  flc_code          TEXT REFERENCES flc_assets(flc_code),
  status            TEXT NOT NULL DEFAULT 'pending'
                         CHECK(status IN ('pending','in-progress','completed','deprecated')),
  man_page_id       TEXT REFERENCES man_pages(gen_id),
  collibra_contract TEXT,                           -- c.contract.* reference
  endpoint_url      TEXT,
  created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ── Seed FLC manifest (1-year mandate 2026-01-01 → 2026-12-31) ───────────────
INSERT OR IGNORE INTO flc_assets
  (flc_code, label, description, asset_type, dw_system, mandate_start, mandate_end, contract_id)
VALUES
  ('MANP','Man Page',         'Generated roff man page from silkpage sidebar metadata',
   'Publication Asset',       'singine',  '2026-01-01','2026-12-31','c.contract.man-pipeline-1yr'),
  ('SIDM','Sidebar Metadata', 'Silkpage XML navigation/sidebar content (TOC entry + page head)',
   'Data Asset',              'singine',  '2026-01-01','2026-12-31','c.contract.man-pipeline-1yr'),
  ('CNTB','Content Block',    'Silkpage XML section element (<section id="...">)',
   'Business Term',           'singine',  '2026-01-01','2026-12-31','c.contract.man-pipeline-1yr'),
  ('DCTZ','Data Citizen',     'Community-active data citizen with public identity',
   'Use Case',                'singine',  '2026-01-01','2026-12-31','c.contract.man-pipeline-1yr'),
  ('MIGR','Migration Service','Mule→SpringBoot service migration record',
   'Data Contract',           'singine',  '2026-01-01','2026-12-31','c.contract.man-pipeline-1yr'),
  ('GOVC','Governance Contract','1-year mandate contract codified in Collibra',
   'Governance Contract',     'collibra', '2026-01-01','2026-12-31','c.contract.man-pipeline-1yr'),
  ('DIMN','DW Dimension',     'Data warehouse dimension mapped to FLC codes',
   'Data Asset',              'singine',  '2026-01-01','2026-12-31','c.contract.man-pipeline-1yr'),
  ('SNGE','Singine Execution','Singine runtime command execution record',
   'Use Case',                'singine',  '2026-01-01','2026-12-31','c.contract.man-pipeline-1yr'),
  ('SILP','Silkpage Asset',   'Silkpage publication page (HTML output)',
   'Publication Asset',       'silkpage', '2026-01-01','2026-12-31','c.contract.man-pipeline-1yr'),
  ('MULE','Mule Service',     'MuleSoft ESB API/integration endpoint (migration source)',
   'Data Asset',              'mule',     '2026-01-01','2026-12-31','c.contract.man-pipeline-1yr'),
  ('SPBT','Spring Boot Svc',  'Spring Boot microservice (migration target)',
   'Data Asset',              'springboot','2026-01-01','2026-12-31','c.contract.man-pipeline-1yr');

-- ── Seed DW dimension axes ────────────────────────────────────────────────────
INSERT OR IGNORE INTO dw_dimensions (gen_id, flc_code, dimension, axis, description) VALUES
  ('dim-manp-main',    'MANP','main',      'subject',       'Man page as primary subject dimension'),
  ('dim-manp-time',    'MANP','temporal',  'time',          'Man page generation timestamp axis'),
  ('dim-sidm-primary', 'SIDM','primary',   'subject',       'Sidebar content as primary source'),
  ('dim-sidm-rel',     'SIDM','relational','operation',     'Sidebar-to-page navigation relation'),
  ('dim-cntb-sec',     'CNTB','secondary', 'subject',       'Section block as secondary dimension'),
  ('dim-dctz-main',    'DCTZ','main',      'data-citizen',  'Community member as citizen dimension'),
  ('dim-dctz-bool',    'DCTZ','boolean',   'operation',     'Active/inactive citizen flag'),
  ('dim-migr-main',    'MIGR','main',      'operation',     'Migration service as operation dimension'),
  ('dim-migr-time',    'MIGR','temporal',  'time',          'Migration timeline axis'),
  ('dim-govc-main',    'GOVC','main',      'operation',     'Governance contract as mandate dimension'),
  ('dim-dimn-nlin',    'DIMN','n_linear',  'subject',       'Multi-dimensional DW axis mapping'),
  ('dim-silp-sec',     'SILP','secondary', 'subject',       'Silkpage HTML as secondary publication'),
  ('dim-mule-rel',     'MULE','relational','operation',     'Mule endpoint as source relation'),
  ('dim-spbt-rel',     'SPBT','relational','operation',     'Spring Boot service as target relation');

INSERT OR IGNORE INTO schema_migrations (version, description, checksum)
VALUES ('V004',
        'Man pages: flc_assets, dw_dimensions, sidebar_entries, man_pages, data_citizens, man_page_citizens, migration_services',
        'sha256:placeholder_V004');
