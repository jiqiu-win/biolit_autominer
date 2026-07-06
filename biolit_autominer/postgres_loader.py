"""Load the conference dataset into PostgreSQL.

Mirrors the approved two-table structure (articles + findings, linked by PMID).
The same DataFrames used for the CSV/Excel exports are written to Postgres, so
the SQL database always matches the published dataset.

Connection is configured via BIOLIT_PG_DSN, e.g.
    export BIOLIT_PG_DSN="host=localhost port=5432 dbname=biolit user=me"
or via the standard libpq environment variables (PGHOST, PGDATABASE, ...).
"""

import os
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from .config import BASE_DIR
from .dataset_database import DatasetDatabase

SCHEMA_PATH = BASE_DIR / "infra" / "postgres" / "schema.sql"

# Exported column name -> database column name.
ARTICLE_COLUMN_MAP = {
    "PMID": "pmid",
    "PMCID": "pmcid",
    "Title": "title",
    "Authors": "authors",
    "Journal": "journal",
    "Publish date": "publish_date",
    "First seen": "first_seen",
    "Downloaded date": "downloaded_date",
    "Last updated": "last_updated",
    "Extracted date": "extracted_date",
    "Source": "source",
    "Gemini processed": "gemini_processed",
    "Finding count": "finding_count",
    "PubMed URL": "pubmed_url",
    "PMC URL": "pmc_url",
}

FINDING_COLUMN_MAP = {
    "Finding ID": "finding_id",
    "PMCID": "pmcid",
    "PMID": "pmid",
    "Tested chemical": "tested_chemical",
    "Subject type": "subject_type",
    "Basic information": "basic_information",
    "Exposure method": "exposure_method",
    "Marker": "marker",
    "Result": "result",
    "Evidence type": "evidence_type",
    "Exposure dose": "exposure_dose",
    "Exposure duration": "exposure_duration",
    "Tissue/organ": "tissue_organ",
    "Evidence sentences": "evidence_sentences",
}

# Columns that must become real NULLs / typed values rather than empty strings.
_TIMESTAMP_COLUMNS = {"first_seen", "downloaded_date", "last_updated", "extracted_date"}


def _clean(value, column):
    """Normalise a DataFrame cell for Postgres insertion."""
    if pd.isna(value):
        return None
    if column == "gemini_processed":
        return str(value).strip().lower() in {"yes", "true", "1"}
    text = str(value).strip()
    if text == "":
        # Empty timestamps must be NULL; empty text stays empty string.
        return None if column in _TIMESTAMP_COLUMNS else ""
    return text


def _rows(df, column_map):
    db_columns = list(column_map.values())
    records = []
    for _, row in df.iterrows():
        records.append(
            tuple(_clean(row.get(src), db) for src, db in column_map.items())
        )
    return db_columns, records


class PostgresLoader:
    def __init__(self, dsn=None):
        # dsn=None -> psycopg2 falls back to PG* environment variables.
        self.dsn = dsn if dsn is not None else os.getenv("BIOLIT_PG_DSN")

    def _connect(self):
        conn = psycopg2.connect(self.dsn) if self.dsn else psycopg2.connect()
        # Findings contain Greek letters / symbols (TNF-alpha, MMP/deltapsi_m, µM).
        conn.set_client_encoding("UTF8")
        return conn

    def create_schema(self, conn):
        conn.cursor().execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()

    def load(self, articles_df, findings_df, refresh=True):
        """Create schema if needed and load both tables (full refresh by default)."""
        conn = self._connect()
        try:
            self.create_schema(conn)
            cur = conn.cursor()
            if refresh:
                # findings first (child), then articles — respects the FK.
                cur.execute("TRUNCATE findings, articles RESTART IDENTITY CASCADE")

            art_cols, art_rows = _rows(articles_df, ARTICLE_COLUMN_MAP)
            if art_rows:
                execute_values(
                    cur,
                    f"INSERT INTO articles ({', '.join(art_cols)}) VALUES %s "
                    "ON CONFLICT (pmid) DO NOTHING",
                    art_rows,
                )

            find_cols, find_rows = _rows(findings_df, FINDING_COLUMN_MAP)
            if find_rows:
                execute_values(
                    cur,
                    f"INSERT INTO findings ({', '.join(find_cols)}) VALUES %s "
                    "ON CONFLICT (finding_id) DO NOTHING",
                    find_rows,
                )

            conn.commit()
            return {"articles": len(art_rows), "findings": len(find_rows)}
        finally:
            conn.close()

    def load_from_dataset(self, dataset_db=None, refresh=True):
        dataset_db = dataset_db or DatasetDatabase()
        return self.load(
            dataset_db.get_articles_df(),
            dataset_db.get_findings_df(),
            refresh=refresh,
        )


def load_dataset_to_postgres(dsn=None, refresh=True):
    return PostgresLoader(dsn).load_from_dataset(refresh=refresh)
