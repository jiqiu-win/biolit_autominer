import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path


class ArticleDatabase:
    """SQLite storage for PubMed articles and sync history."""

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()

    def _connect(self):
        """Every caller gets its own connection (no shared state across threads).
        WAL mode was tried here for concurrent-writer support, but caused real
        corruption on Wahab's network-attached storage -- even from a single
        writer with no concurrency at all. WAL relies on memory-mapped shared
        files that many network filesystems don't support reliably. Using the
        default rollback journal instead: slower under concurrent writes, but
        does not corrupt data. busy_timeout still helps writers wait their turn
        instead of erroring immediately."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = DELETE")
        return conn

    def init_database(self):
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                pmid TEXT PRIMARY KEY,
                pmcid TEXT,
                title TEXT,
                authors TEXT,
                pub_date TEXT,
                journal TEXT,
                abstract TEXT,
                status TEXT,
                has_full_text INTEGER,
                source TEXT,
                full_text_url TEXT,
                content_hash TEXT,
                gemini_processed INTEGER DEFAULT 0,
                gemini_result TEXT,
                error_message TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                download_status TEXT,
                download_error TEXT,
                extraction_error TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pmid TEXT NOT NULL,
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
                extracted_at TIMESTAMP,
                UNIQUE(pmid, tested_chemical, marker, result, evidence_sentences)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_date TIMESTAMP,
                search_query TEXT,
                total_found INTEGER,
                new_count INTEGER,
                modified_count INTEGER,
                unchanged_count INTEGER,
                processed_count INTEGER,
                skipped_count INTEGER,
                time_saved_pct REAL,
                duration_seconds REAL,
                notes TEXT
            )
            """
        )

        self._ensure_columns(cursor)
        self._ensure_sync_log_schema(cursor)
        conn.commit()
        conn.close()

    def _ensure_sync_log_schema(self, cursor):
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_log'"
        )
        if not cursor.fetchone():
            return

        cursor.execute("PRAGMA table_info(sync_log)")
        columns = {row[1] for row in cursor.fetchall()}
        expected = {
            "id",
            "sync_date",
            "search_query",
            "total_found",
            "new_count",
            "modified_count",
            "unchanged_count",
            "processed_count",
            "skipped_count",
            "time_saved_pct",
            "duration_seconds",
            "notes",
        }
        if columns == expected:
            return

        cursor.execute("ALTER TABLE sync_log RENAME TO sync_log_legacy")
        cursor.execute(
            """
            CREATE TABLE sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_date TIMESTAMP,
                search_query TEXT,
                total_found INTEGER,
                new_count INTEGER,
                modified_count INTEGER,
                unchanged_count INTEGER,
                processed_count INTEGER,
                skipped_count INTEGER,
                time_saved_pct REAL,
                duration_seconds REAL,
                notes TEXT
            )
            """
        )

    def _ensure_columns(self, cursor):
        """Add new columns to older databases without losing data."""
        cursor.execute("PRAGMA table_info(articles)")
        columns = {row[1] for row in cursor.fetchall()}
        migrations = {
            "abstract": "TEXT",
            "content_hash": "TEXT",
            "local_file_path": "TEXT",
            "local_pdf_path": "TEXT",
            "download_status": "TEXT",
            "download_error": "TEXT",
            "extraction_error": "TEXT",
        }
        for column, col_type in migrations.items():
            if column not in columns:
                cursor.execute(f"ALTER TABLE articles ADD COLUMN {column} {col_type}")

    @staticmethod
    def compute_content_hash(metadata):
        """Hash key metadata fields to detect when PubMed updates an article."""
        parts = [
            metadata.get("title") or "",
            metadata.get("authors") or "",
            metadata.get("journal") or "",
            metadata.get("pub_date") or "",
            metadata.get("abstract") or "",
        ]
        payload = "|".join(parts).strip().lower()
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def add_article(self, pmid, data):
        conn = self._connect()
        cursor = conn.cursor()
        now = datetime.now()

        cursor.execute(
            """
            SELECT created_at, gemini_processed, gemini_result, extraction_error
            FROM articles WHERE pmid = ?
            """,
            (pmid,),
        )
        row = cursor.fetchone()
        created_at = row[0] if row else now
        # INSERT OR REPLACE deletes-then-reinserts the row, so any column left out
        # here would silently reset to its default. Carry these forward explicitly
        # so re-importing/re-syncing an article never wipes out Gemini progress.
        gemini_processed = row[1] if row else 0
        gemini_result = row[2] if row else None
        # extraction_error is only ever set by mark_extraction_failed() / cleared by
        # mark_gemini_processed() -- never by the data passed in here, so just carry
        # forward whatever is already there.
        extraction_error = row[3] if row else None

        cursor.execute(
            """
            INSERT OR REPLACE INTO articles
            (pmid, pmcid, title, authors, pub_date, journal, abstract, status,
             has_full_text, source, full_text_url, content_hash, local_file_path,
             local_pdf_path, error_message, created_at, updated_at,
             gemini_processed, gemini_result, download_status, download_error,
             extraction_error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pmid,
                data.get("pmcid"),
                data.get("title"),
                data.get("authors"),
                data.get("pub_date"),
                data.get("journal"),
                data.get("abstract"),
                data.get("status", "new"),
                int(bool(data.get("has_full_text", 0))),
                data.get("source"),
                data.get("full_text_url"),
                data.get("content_hash"),
                data.get("local_file_path"),
                data.get("local_pdf_path"),
                data.get("error_message"),
                created_at,
                now,
                gemini_processed,
                gemini_result,
                data.get("download_status"),
                data.get("download_error"),
                extraction_error,
            ),
        )

        conn.commit()
        conn.close()

    def get_article(self, pmid):
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM articles WHERE pmid = ?", (pmid,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_local_file_path(self, pmid, txt_path, pdf_path=None):
        conn = self._connect()
        cursor = conn.cursor()
        if pdf_path is not None:
            cursor.execute(
                """
                UPDATE articles
                SET local_file_path = ?, local_pdf_path = ?, updated_at = ?
                WHERE pmid = ?
                """,
                (str(txt_path), str(pdf_path) if pdf_path else None, datetime.now(), str(pmid)),
            )
        else:
            cursor.execute(
                """
                UPDATE articles
                SET local_file_path = ?, updated_at = ?
                WHERE pmid = ?
                """,
                (str(txt_path), datetime.now(), str(pmid)),
            )
        conn.commit()
        conn.close()

    def get_existing_pmids(self):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT pmid FROM articles")
        pmids = {row[0] for row in cursor.fetchall()}
        conn.close()
        return pmids

    def get_hash_map(self):
        """Return {pmid: content_hash} for incremental change detection."""
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT pmid, content_hash FROM articles")
        result = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        return result

    def log_sync(self, sync_data):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sync_log
            (sync_date, search_query, total_found, new_count, modified_count,
             unchanged_count, processed_count, skipped_count, time_saved_pct,
             duration_seconds, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(),
                sync_data.get("search_query"),
                sync_data.get("total_found", 0),
                sync_data.get("new_count", 0),
                sync_data.get("modified_count", 0),
                sync_data.get("unchanged_count", 0),
                sync_data.get("processed_count", 0),
                sync_data.get("skipped_count", 0),
                sync_data.get("time_saved_pct", 0.0),
                sync_data.get("duration_seconds", 0.0),
                sync_data.get("notes", ""),
            ),
        )
        conn.commit()
        conn.close()

    def export_sync_history(self, output_path):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT sync_date, search_query, total_found, new_count, modified_count,
                   unchanged_count, processed_count, skipped_count, time_saved_pct,
                   duration_seconds, notes
            FROM sync_log
            ORDER BY sync_date DESC
            """
        )
        rows = cursor.fetchall()
        conn.close()

        history = [
            {
                "sync_date": row[0],
                "search_query": row[1],
                "total_found": row[2],
                "new_count": row[3],
                "modified_count": row[4],
                "unchanged_count": row[5],
                "processed_count": row[6],
                "skipped_count": row[7],
                "time_saved_pct": row[8],
                "duration_seconds": row[9],
                "notes": row[10],
            }
            for row in rows
        ]

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
        print(f"Exported sync history to {output_path}")

    def export_to_excel(self, output_path):
        try:
            import pandas as pd

            from .excel_exporter import export_articles_to_excel

            conn = self._connect()
            df = pd.read_sql_query("SELECT * FROM articles ORDER BY pmid", conn)
            conn.close()
            export_articles_to_excel(df, output_path)
            print(f"Exported to {output_path}")
        except Exception as exc:
            print(f"Export failed: {exc}")

    def mark_gemini_processed(self, pmid, cache_path, raw_response=""):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE articles
            SET gemini_processed = 1,
                gemini_result = ?,
                extraction_error = NULL,
                updated_at = ?
            WHERE pmid = ?
            """,
            (raw_response[:50000] if raw_response else None, datetime.now(), pmid),
        )
        conn.commit()
        conn.close()

    def mark_extraction_failed(self, pmid, error_message):
        """Record a Gemini/extraction failure. gemini_processed stays 0 (unchanged
        meaning), but extraction_error now distinguishes "attempted and failed"
        from "never attempted" -- previously nothing was written on failure at all."""
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE articles
            SET extraction_error = ?,
                updated_at = ?
            WHERE pmid = ?
            """,
            (str(error_message)[:2000] if error_message else None, datetime.now(), pmid),
        )
        conn.commit()
        conn.close()

    def add_finding(self, pmid, finding):
        """Insert one structured finding row, written directly at extraction time
        rather than reconstructed later from raw text. Safe to call repeatedly on
        the same finding (dedup via UNIQUE constraint, last write wins)."""
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO findings
            (pmid, tested_chemical, subject_type, basic_information, exposure_method,
             marker, result, evidence_type, exposure_dose, exposure_duration,
             tissue_organ, evidence_sentences, extracted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pmid,
                finding.get("tested_chemical"),
                finding.get("subject_type"),
                finding.get("basic_information"),
                finding.get("exposure_method"),
                finding.get("marker"),
                finding.get("result"),
                finding.get("evidence_type"),
                finding.get("exposure_dose"),
                finding.get("exposure_duration"),
                finding.get("tissue_organ"),
                finding.get("evidence_sentences"),
                datetime.now(),
            ),
        )
        conn.commit()
        conn.close()

    def get_findings(self, pmid=None):
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if pmid:
            cursor.execute("SELECT * FROM findings WHERE pmid = ? ORDER BY id", (pmid,))
        else:
            cursor.execute("SELECT * FROM findings ORDER BY pmid, id")
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_articles_for_extraction(self, pmids=None):
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if pmids:
            # SQLite has a hard limit (~1000) on placeholders in a single query --
            # a large pmids list (e.g. the full remaining backlog) would blow past
            # that in one "WHERE pmid IN (...)" call, so fetch in safe-sized chunks
            # and combine the results instead.
            pmids = list(pmids)
            chunk_size = 500
            rows = []
            for i in range(0, len(pmids), chunk_size):
                chunk = pmids[i : i + chunk_size]
                placeholders = ",".join("?" for _ in chunk)
                cursor.execute(
                    f"""
                    SELECT pmid, pmcid, title, source, local_file_path, gemini_processed
                    FROM articles
                    WHERE pmid IN ({placeholders})
                    ORDER BY pmid
                    """,
                    chunk,
                )
                rows.extend(dict(row) for row in cursor.fetchall())
            conn.close()
            return rows
        else:
            cursor.execute(
                """
                SELECT pmid, pmcid, title, source, local_file_path, gemini_processed
                FROM articles
                WHERE local_file_path IS NOT NULL
                ORDER BY pmid
                """
            )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_unprocessed_full_text_pmids(self, limit=None, year_start=None, year_end=None):
        """PMIDs with PMC text saved (full text or abstract-only) but not yet
        sent to Gemini. has_full_text is not filtered on here -- it stays as
        accurate metadata distinguishing full text from abstract-only content,
        but both are eligible for extraction; local_file_path is what matters.

        year_start/year_end filter on the first 4 characters of pub_date, so a
        backlog batch (e.g. one HPC array task per year range) can be selected
        without touching articles outside that range.
        """
        conn = self._connect()
        cursor = conn.cursor()
        query = """
            SELECT pmid FROM articles
            WHERE local_file_path IS NOT NULL
              AND source LIKE 'pmc%'
              AND (gemini_processed IS NULL OR gemini_processed = 0)
        """
        params = []
        if year_start is not None:
            query += " AND CAST(substr(pub_date, 1, 4) AS INTEGER) >= ?"
            params.append(year_start)
        if year_end is not None:
            query += " AND CAST(substr(pub_date, 1, 4) AS INTEGER) <= ?"
            params.append(year_end)
        query += " ORDER BY pmid"
        cursor.execute(query, params)
        pmids = [row[0] for row in cursor.fetchall()]
        conn.close()
        if limit is not None:
            pmids = pmids[:limit]
        return pmids

    def get_stats(self):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM articles")
        total = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM articles WHERE status = "processed"')
        processed = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM articles WHERE status = "new"')
        new = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM articles WHERE status = "modified"')
        modified = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM articles WHERE gemini_processed = 1")
        gemini_processed = cursor.fetchone()[0]
        conn.close()
        return {
            "total_articles": total,
            "processed": processed,
            "new": new,
            "modified": modified,
            "gemini_processed": gemini_processed,
        }

    def print_stats(self):
        stats = self.get_stats()
        print(
            f"Total articles: {stats['total_articles']} | "
            f"Processed: {stats['processed']} | "
            f"New: {stats['new']} | Modified: {stats['modified']}"
        )
