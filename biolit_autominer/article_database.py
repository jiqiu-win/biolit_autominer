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

    def init_database(self):
        conn = sqlite3.connect(self.db_path)
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
                updated_at TIMESTAMP
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
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now()

        cursor.execute("SELECT created_at FROM articles WHERE pmid = ?", (pmid,))
        row = cursor.fetchone()
        created_at = row[0] if row else now

        cursor.execute(
            """
            INSERT OR REPLACE INTO articles
            (pmid, pmcid, title, authors, pub_date, journal, abstract, status,
             has_full_text, source, full_text_url, content_hash, local_file_path,
             local_pdf_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                created_at,
                now,
            ),
        )

        conn.commit()
        conn.close()

    def get_article(self, pmid):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM articles WHERE pmid = ?", (pmid,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_existing_pmids(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT pmid FROM articles")
        pmids = {row[0] for row in cursor.fetchall()}
        conn.close()
        return pmids

    def get_hash_map(self):
        """Return {pmid: content_hash} for incremental change detection."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT pmid, content_hash FROM articles")
        result = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        return result

    def log_sync(self, sync_data):
        conn = sqlite3.connect(self.db_path)
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
        conn = sqlite3.connect(self.db_path)
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

            conn = sqlite3.connect(self.db_path)
            df = pd.read_sql_query("SELECT * FROM articles ORDER BY pmid", conn)
            conn.close()
            export_articles_to_excel(df, output_path)
            print(f"Exported to {output_path}")
        except Exception as exc:
            print(f"Export failed: {exc}")

    def mark_gemini_processed(self, pmid, cache_path, raw_response=""):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE articles
            SET gemini_processed = 1,
                gemini_result = ?,
                updated_at = ?
            WHERE pmid = ?
            """,
            (raw_response[:50000] if raw_response else None, datetime.now(), pmid),
        )
        conn.commit()
        conn.close()

    def get_articles_for_extraction(self, pmids=None):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if pmids:
            placeholders = ",".join("?" for _ in pmids)
            cursor.execute(
                f"""
                SELECT pmid, pmcid, title, source, local_file_path, gemini_processed
                FROM articles
                WHERE pmid IN ({placeholders})
                ORDER BY pmid
                """,
                list(pmids),
            )
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

    def get_stats(self):
        conn = sqlite3.connect(self.db_path)
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
