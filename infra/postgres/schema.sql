-- Biolit AutoMiner — PostgreSQL schema
-- Conference dataset: hepatotoxicity & mitochondrial-toxicity literature mining.
--
-- Two normalized tables linked by PMID (mirrors the approved CSV/Excel structure):
--   articles  — one row per PubMed/PMC article (metadata, source type, tracking, URLs)
--   findings  — one row per Gemini-extracted finding, linked to its article by PMID
--
-- Apply on the server with:
--   psql -d biolit -f infra/postgres/schema.sql

CREATE TABLE IF NOT EXISTS articles (
    pmid             TEXT PRIMARY KEY,
    pmcid            TEXT,
    title            TEXT,
    authors          TEXT,
    journal          TEXT,
    publish_date     TEXT,          -- PubMed dates are free-form ("2026", "2026 Jan"); kept as text
    first_seen       TIMESTAMP,
    downloaded_date  TIMESTAMP,
    last_updated     TIMESTAMP,
    extracted_date   TIMESTAMP,
    source           TEXT,          -- 'Full text' or 'Abstract'
    gemini_processed BOOLEAN DEFAULT FALSE,
    finding_count    INTEGER DEFAULT 0,
    pubmed_url       TEXT,
    pmc_url          TEXT
);

CREATE TABLE IF NOT EXISTS findings (
    finding_id         INTEGER PRIMARY KEY,
    pmid               TEXT NOT NULL REFERENCES articles(pmid) ON DELETE CASCADE,
    pmcid              TEXT,
    tested_chemical    TEXT,
    subject_type       TEXT,
    basic_information  TEXT,
    exposure_method    TEXT,
    marker             TEXT,
    result             TEXT,
    evidence_type      TEXT,
    exposure_dose      TEXT,
    exposure_duration  TEXT,
    tissue_organ       TEXT,
    evidence_sentences TEXT
);

-- Indexes for the common "find the key info" queries.
CREATE INDEX IF NOT EXISTS idx_findings_pmid            ON findings (pmid);
CREATE INDEX IF NOT EXISTS idx_findings_marker          ON findings (marker);
CREATE INDEX IF NOT EXISTS idx_findings_result          ON findings (result);
CREATE INDEX IF NOT EXISTS idx_findings_subject_type    ON findings (subject_type);
CREATE INDEX IF NOT EXISTS idx_findings_tested_chemical ON findings (tested_chemical);
CREATE INDEX IF NOT EXISTS idx_articles_source          ON articles (source);
