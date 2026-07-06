"""
User-facing dataset database for conference submission.

Combines article metadata (PubMed/PMC, publish date, download date) with
Gemini 2.5 extraction rows. Refreshed automatically after each daily run.

Outputs:
  auto_pipeline_output/biolit_dataset.db      — SQLite (queryable)
  auto_pipeline_output/updated/biolit_dataset.xlsx — Excel (PI-friendly)
  auto_pipeline_output/updated/biolit_findings.csv
  auto_pipeline_output/updated/biolit_articles.csv
"""

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .config import config
from .extraction_exporter import build_rows_from_cache
from .excel_exporter import ALT_ROW_FILL, HEADER_FILL, HEADER_FONT, WHITE_FILL

FINDINGS_COLUMNS = [
    "Finding ID",
    "PMCID",
    "PMID",
    "Tested chemical",
    "Subject type",
    "Basic information",
    "Exposure method",
    "Marker",
    "Result",
    "Evidence type",
    "Exposure dose",
    "Exposure duration",
    "Tissue/organ",
    "Evidence sentences",
]

ARTICLES_COLUMNS = [
    "PMID",
    "PMCID",
    "Title",
    "Authors",
    "Journal",
    "Publish date",
    "First seen",
    "Downloaded date",
    "Last updated",
    "Extracted date",
    "Source",
    "Gemini processed",
    "Finding count",
    "PubMed URL",
    "PMC URL",
]

FINDING_WIDTHS = {
    "Finding ID": 10,
    "PMCID": 14,
    "PMID": 12,
    "Tested chemical": 22,
    "Subject type": 14,
    "Basic information": 20,
    "Exposure method": 16,
    "Marker": 14,
    "Result": 20,
    "Evidence type": 16,
    "Exposure dose": 18,
    "Exposure duration": 18,
    "Tissue/organ": 18,
    "Evidence sentences": 60,
}

ARTICLE_WIDTHS = {
    "PMID": 12,
    "PMCID": 14,
    "Title": 45,
    "Authors": 30,
    "Journal": 24,
    "Publish date": 14,
    "First seen": 20,
    "Downloaded date": 20,
    "Last updated": 20,
    "Extracted date": 20,
    "Source": 16,
    "Gemini processed": 14,
    "Finding count": 14,
    "PubMed URL": 18,
    "PMC URL": 18,
}

ABOUT_FILL = PatternFill(fill_type="solid", fgColor="E8F0FE")
ABOUT_FONT = Font(bold=True, color="1F4E79")


def _fmt_ts(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    text = str(value)
    if "T" in text:
        text = text.replace("T", " ")[:19]
    return text[:19]


def _pubmed_url(pmid):
    return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""


def _pmc_url(pmcid):
    pmcid = config.format_pmcid(pmcid) if pmcid else ""
    return f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else ""


def _download_method(source):
    if pd.isna(source) or not source:
        return ""
    if source == "pmc_full_text":
        return "PMC full text"
    if source.startswith("pmc"):
        return source.replace("_", " ")
    if source == "pubmed_abstract":
        return "PubMed abstract"
    return source


def _source_label(source):
    """Human-friendly source type: 'Full text' vs 'Abstract'."""
    if pd.isna(source) or not source:
        return ""
    key = str(source).strip().lower()
    if key.startswith("pubmed"):
        return "Abstract"
    if key.startswith("pmc"):
        return "Full text"
    return _download_method(source)


# Fields that carry the actual extracted science. A finding row with all of these
# empty is a "No results" placeholder (common for abstracts) and is hidden from
# the exported Findings table so the dataset stays clean.
_FINDING_CONTENT_FIELDS = (
    "tested_chemical",
    "subject_type",
    "basic_information",
    "exposure_method",
    "marker",
    "result",
    "evidence_type",
    "exposure_dose",
    "exposure_duration",
    "tissue_organ",
    "evidence_sentences",
)


def _is_empty_finding(row):
    """True when a finding carries no extracted content (a 'No results' placeholder)."""
    for field in _FINDING_CONTENT_FIELDS:
        value = row.get(field, "")
        if not (pd.isna(value) or str(value).strip() == ""):
            return False
    return True


class DatasetDatabase:
    """SQLite dataset combining articles + Gemini findings for conference use."""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path or config.DATASET_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_articles (
                pmid TEXT PRIMARY KEY,
                pmcid TEXT,
                title TEXT,
                authors TEXT,
                journal TEXT,
                pub_date TEXT,
                abstract TEXT,
                has_full_text INTEGER,
                source TEXT,
                source_file TEXT,
                local_file_path TEXT,
                first_seen_at TEXT,
                downloaded_at TEXT,
                last_updated_at TEXT,
                extracted_at TEXT,
                gemini_processed INTEGER DEFAULT 0,
                finding_count INTEGER DEFAULT 0,
                pubmed_url TEXT,
                pmc_url TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pmid TEXT NOT NULL,
                pmcid TEXT,
                source_file TEXT,
                updated_time TEXT,
                tested_chemical TEXT,
                subject_type TEXT,
                basic_information TEXT,
                exposure_method TEXT,
                marker TEXT,
                result TEXT,
                evidence_type TEXT,
                exposure_dose TEXT,
                exposure_duration TEXT,
                tissue_organ TEXT,
                evidence_sentences TEXT,
                chain_of_thought TEXT,
                gemini_raw_output TEXT,
                extracted_at TEXT,
                UNIQUE(pmid, tested_chemical, marker, result, evidence_sentences)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        conn.commit()
        conn.close()

    @staticmethod
    def _source_file_for_article(row):
        pmid = row["pmid"]
        pmcid = row.get("pmcid") or ""
        title = row.get("title") or ""
        source = row.get("source") or ""
        if source == "pubmed_abstract":
            return config.abstract_filename(pmid)
        if source.startswith("pmc"):
            return config.pmc_filename(pmid, pmcid, title)
        local_path = row.get("local_file_path")
        return Path(local_path).name if local_path else pmid

    @staticmethod
    def _gemini_path_for_article(row):
        pmid = row["pmid"]
        pmcid = row.get("pmcid") or ""
        title = row.get("title") or ""
        source = row.get("source") or ""
        if source == "pubmed_abstract":
            return config.abstract_gemini_path(pmid)
        if source.startswith("pmc"):
            return config.pmc_gemini_path(pmid, pmcid, title)
        return None

    def sync_from_article_db(self, article_db):
        """Rebuild dataset tables from articles.db and Gemini cache."""
        import sqlite3 as sqlite

        conn = sqlite.connect(article_db.db_path)
        conn.row_factory = sqlite.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM articles ORDER BY pmid")
        article_rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cot_dir = config.GEMINI_CACHE_DIR / "chain_of_thought"

        ds_conn = self._connect()
        ds_cursor = ds_conn.cursor()
        ds_cursor.execute("DELETE FROM dataset_findings")
        ds_cursor.execute("DELETE FROM dataset_articles")

        total_findings = 0
        gemini_articles = 0

        for row in article_rows:
            pmid = str(row["pmid"])
            pmcid = row.get("pmcid") or ""
            source_file = self._source_file_for_article(row)
            gemini_processed = int(row.get("gemini_processed") or 0)
            has_full_text = int(row.get("has_full_text") or 0)
            downloaded_at = _fmt_ts(row.get("created_at"))
            extracted_at = _fmt_ts(row.get("updated_at")) if gemini_processed else ""

            ds_cursor.execute(
                """
                INSERT OR REPLACE INTO dataset_articles
                (pmid, pmcid, title, authors, journal, pub_date, abstract,
                 has_full_text, source, source_file, local_file_path,
                 first_seen_at, downloaded_at, last_updated_at, extracted_at,
                 gemini_processed, finding_count, pubmed_url, pmc_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pmid,
                    pmcid,
                    row.get("title"),
                    row.get("authors"),
                    row.get("journal"),
                    row.get("pub_date"),
                    row.get("abstract"),
                    has_full_text,
                    row.get("source"),
                    source_file,
                    row.get("local_file_path"),
                    _fmt_ts(row.get("created_at")),
                    downloaded_at,
                    _fmt_ts(row.get("updated_at")),
                    extracted_at,
                    gemini_processed,
                    0,
                    _pubmed_url(pmid),
                    _pmc_url(pmcid),
                ),
            )

            gemini_path = self._gemini_path_for_article(row)
            if not gemini_path or not gemini_path.is_file():
                continue

            gemini_articles += 1
            cot_path = None
            if row.get("source") == "pubmed_abstract":
                cot_path = cot_dir / f"PM{pmid}_abstract_chain_of_thought.txt"
            elif row.get("source", "").startswith("pmc"):
                cot_path = cot_dir / f"{Path(source_file).stem}_chain_of_thought.txt"

            parsed_rows = build_rows_from_cache(source_file, gemini_path, cot_path)
            finding_count = 0
            for parsed in parsed_rows:
                extracted_time = parsed.get("Updated time") or now
                ds_cursor.execute(
                    """
                    INSERT OR REPLACE INTO dataset_findings
                    (pmid, pmcid, source_file, updated_time,
                     tested_chemical, subject_type, basic_information,
                     exposure_method, marker, result, evidence_type,
                     exposure_dose, exposure_duration, tissue_organ,
                     evidence_sentences, chain_of_thought, gemini_raw_output,
                     extracted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pmid,
                        pmcid,
                        source_file,
                        extracted_time,
                        parsed.get("Tested chemical"),
                        parsed.get("Subject type"),
                        parsed.get("Basic information"),
                        parsed.get("Exposure method"),
                        parsed.get("Marker"),
                        parsed.get("Result"),
                        parsed.get("Evidence type"),
                        parsed.get("Exposure dose"),
                        parsed.get("Exposure duration"),
                        parsed.get("Tissue/organ"),
                        parsed.get("Evidence sentences"),
                        parsed.get("Chain of thought for deriving evidence"),
                        parsed.get("Gemini raw output"),
                        extracted_time,
                    ),
                )
                finding_count += 1
                total_findings += 1

            ds_cursor.execute(
                "UPDATE dataset_articles SET finding_count = ? WHERE pmid = ?",
                (finding_count, pmid),
            )

        ds_cursor.execute(
            "INSERT OR REPLACE INTO dataset_meta (key, value) VALUES (?, ?)",
            ("last_sync_at", now),
        )
        ds_cursor.execute(
            "INSERT OR REPLACE INTO dataset_meta (key, value) VALUES (?, ?)",
            ("article_count", str(len(article_rows))),
        )
        ds_cursor.execute(
            "INSERT OR REPLACE INTO dataset_meta (key, value) VALUES (?, ?)",
            ("finding_count", str(total_findings)),
        )
        ds_cursor.execute(
            "INSERT OR REPLACE INTO dataset_meta (key, value) VALUES (?, ?)",
            ("gemini_article_count", str(gemini_articles)),
        )
        ds_conn.commit()
        ds_conn.close()

        export_paths = self.export_all(now)
        print(
            f"Dataset synced: {len(article_rows)} articles, "
            f"{total_findings} findings ({gemini_articles} with Gemini output)"
        )
        return {
            "article_count": len(article_rows),
            "finding_count": total_findings,
            "gemini_article_count": gemini_articles,
            "last_sync_at": now,
            **export_paths,
        }

    def get_findings_df(self):
        conn = self._connect()
        articles = pd.read_sql_query("SELECT * FROM dataset_articles", conn)
        findings = pd.read_sql_query("SELECT * FROM dataset_findings ORDER BY pmid, id", conn)
        conn.close()

        if findings.empty:
            return pd.DataFrame(columns=FINDINGS_COLUMNS)

        art = articles.set_index("pmid")
        rows = []
        finding_id = 0
        for _, f in findings.iterrows():
            if _is_empty_finding(f):
                continue
            finding_id += 1
            pmid = f["pmid"]
            a = art.loc[pmid] if pmid in art.index else {}
            pmcid = f.get("pmcid") or (a.get("pmcid") if hasattr(a, "get") else "")
            rows.append(
                {
                    "Finding ID": finding_id,
                    "PMCID": pmcid,
                    "PMID": pmid,
                    "Tested chemical": f.get("tested_chemical", ""),
                    "Subject type": f.get("subject_type", ""),
                    "Basic information": f.get("basic_information", ""),
                    "Exposure method": f.get("exposure_method", ""),
                    "Marker": f.get("marker", ""),
                    "Result": f.get("result", ""),
                    "Evidence type": f.get("evidence_type", ""),
                    "Exposure dose": f.get("exposure_dose", ""),
                    "Exposure duration": f.get("exposure_duration", ""),
                    "Tissue/organ": f.get("tissue_organ", ""),
                    "Evidence sentences": f.get("evidence_sentences", ""),
                }
            )
        return pd.DataFrame(rows, columns=FINDINGS_COLUMNS)

    def get_articles_df(self):
        conn = self._connect()
        df = pd.read_sql_query(
            """
            SELECT pmid, pmcid, title, authors, journal, pub_date,
                   first_seen_at, downloaded_at, last_updated_at, extracted_at,
                   has_full_text, source, gemini_processed, finding_count,
                   pubmed_url, pmc_url
            FROM dataset_articles
            ORDER BY pmid
            """,
            conn,
        )
        findings = pd.read_sql_query("SELECT * FROM dataset_findings", conn)
        conn.close()
        if df.empty:
            return pd.DataFrame(columns=ARTICLES_COLUMNS)

        # Count only real findings (exclude "No results" placeholders) so the
        # Articles "Finding count" agrees with the rows shown in the Findings table.
        if findings.empty:
            real_counts = {}
        else:
            real = findings[~findings.apply(_is_empty_finding, axis=1)]
            real_counts = real.groupby("pmid").size().to_dict()

        df = df.rename(
            columns={
                "pmid": "PMID",
                "pmcid": "PMCID",
                "title": "Title",
                "authors": "Authors",
                "journal": "Journal",
                "pub_date": "Publish date",
                "first_seen_at": "First seen",
                "downloaded_at": "Downloaded date",
                "last_updated_at": "Last updated",
                "extracted_at": "Extracted date",
                "pubmed_url": "PubMed URL",
                "pmc_url": "PMC URL",
            }
        )
        df["Source"] = df["source"].apply(_source_label)
        df["Gemini processed"] = df["gemini_processed"].apply(lambda x: "Yes" if x else "No")
        df["Finding count"] = df["PMID"].map(lambda p: real_counts.get(p, 0)).astype(int)
        return df[ARTICLES_COLUMNS]

    def get_meta(self):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM dataset_meta")
        meta = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        return meta

    def _style_sheet(self, ws, column_widths, data_row_height=60):
        for col_idx in range(1, ws.max_column + 1):
            header = ws.cell(row=1, column=col_idx).value
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            width = column_widths.get(str(header), 18)
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        for row_idx in range(2, ws.max_row + 1):
            row_fill = ALT_ROW_FILL if row_idx % 2 == 0 else WHITE_FILL
            ws.row_dimensions[row_idx].height = data_row_height
            for col_idx in range(1, ws.max_column + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.fill = row_fill
                cell.alignment = Alignment(vertical="top", wrap_text=True)
        ws.freeze_panes = "A2"

    def _write_about_sheet(self, wb, sync_time):
        if "About" in wb.sheetnames:
            del wb["About"]
        ws = wb.create_sheet("About", 0)
        meta = self.get_meta()
        real_finding_count = len(self.get_findings_df())
        lines = [
            ("Biolit AutoMiner — Conference Dataset", ""),
            ("", ""),
            ("Description", "Hepatotoxicity & mitochondrial toxicity literature dataset"),
            ("Search scope", "PubMed query from prompts.py (ALT, AST, MDA, liver injury, etc.)"),
            ("Extraction model", f"Gemini 2.5 ({config.GEMINI_MODEL}) via Vertex AI"),
            ("Last updated", sync_time),
            ("Total articles", meta.get("article_count", "0")),
            ("Articles with Gemini output", meta.get("gemini_article_count", "0")),
            ("Total findings (rows)", real_finding_count),
            ("", ""),
            ("Structure", "Normalized: two tables linked by PMID"),
            ("Sheets", ""),
            ("  Findings", "One row per extracted finding (main dataset). Join to Articles on PMID."),
            ("  Articles", "One row per article (metadata, source type, tracking dates, URLs)."),
            ("", ""),
            ("Key columns", ""),
            ("  Finding ID", "Unique ID for each extracted finding row"),
            ("  PMID / PMCID", "Article identifiers; link Findings to Articles"),
            ("  Source", "Full text (PMC) or Abstract (PubMed only)"),
            ("  Publish date", "Article publication date from PubMed"),
            ("  Downloaded date", "When our pipeline first retrieved the article"),
            ("  Extracted date", "When Gemini 2.5 processed the article"),
            ("  PubMed URL / PMC URL", "One-click links to the original article"),
            ("", ""),
            ("Daily update", "Refreshed automatically after each daily PMC run"),
            ("CSV exports", "biolit_findings.csv, biolit_articles.csv (same folder)"),
            ("SQLite database", str(self.db_path)),
        ]
        for row_idx, (label, value) in enumerate(lines, start=1):
            ws.cell(row=row_idx, column=1, value=label)
            ws.cell(row=row_idx, column=2, value=value)
            if label and not value and row_idx == 1:
                ws.cell(row=row_idx, column=1).font = Font(bold=True, size=14, color="1F4E79")
            elif label in {
                "Description",
                "Last updated",
                "Total articles",
                "Total findings (rows)",
                "Sheets",
                "Key columns",
            }:
                ws.cell(row=row_idx, column=1).font = ABOUT_FONT
                ws.cell(row=row_idx, column=1).fill = ABOUT_FILL
        ws.column_dimensions["A"].width = 28
        ws.column_dimensions["B"].width = 70

    def export_excel(self, sync_time=None):
        sync_time = sync_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        output_path = config.DATASET_XLSX_PATH
        output_path.parent.mkdir(parents=True, exist_ok=True)

        findings_df = self.get_findings_df()
        articles_df = self.get_articles_df()

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            findings_df.to_excel(writer, sheet_name="Findings", index=False)
            articles_df.to_excel(writer, sheet_name="Articles", index=False)

        wb = load_workbook(output_path)
        self._write_about_sheet(wb, sync_time)
        self._style_sheet(wb["Findings"], FINDING_WIDTHS)
        self._style_sheet(wb["Articles"], ARTICLE_WIDTHS, data_row_height=45)
        wb.save(output_path)
        print(f"Dataset Excel saved to {output_path}")
        return output_path

    def export_csv(self):
        config.UPDATED_DIR.mkdir(parents=True, exist_ok=True)
        findings_path = config.DATASET_FINDINGS_CSV
        articles_path = config.DATASET_ARTICLES_CSV
        self.get_findings_df().to_csv(findings_path, index=False)
        self.get_articles_df().to_csv(articles_path, index=False)
        print(f"Dataset CSV saved to {findings_path} and {articles_path}")
        return {"findings_csv": findings_path, "articles_csv": articles_path}

    def export_all(self, sync_time=None):
        sync_time = sync_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        xlsx = self.export_excel(sync_time)
        csv_paths = self.export_csv()
        return {"dataset_xlsx": xlsx, **csv_paths, "dataset_db": self.db_path}

    def get_stats(self):
        meta = self.get_meta()
        return {
            "article_count": int(meta.get("article_count", 0)),
            "finding_count": int(meta.get("finding_count", 0)),
            "gemini_article_count": int(meta.get("gemini_article_count", 0)),
            "last_sync_at": meta.get("last_sync_at", ""),
        }


def sync_dataset_from_pipeline(article_db):
    """Convenience entry point used by the daily pipeline."""
    return DatasetDatabase().sync_from_article_db(article_db)
