"""
Sync incrementally updated files into auto_pipeline_output/updated/.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

from .config import config


class UpdateReportWriter:
    """Copy new/modified article files into updated/ after each pipeline run."""

    def __init__(self, output_dir=None, frequency=None):
        self.output_dir = Path(output_dir or config.OUTPUT_DIR)
        self.frequency = frequency or config.UPDATE_FREQUENCY

    def _copy_if_exists(self, source, destination):
        source = Path(source)
        destination = Path(destination)
        if not source.is_file():
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return True

    def sync_files_to_updated(self, db, pmids=None):
        import sqlite3

        connection = sqlite3.connect(db.db_path)
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        if pmids:
            placeholders = ",".join("?" for _ in pmids)
            cursor.execute(
                f"""
                SELECT pmid, pmcid, source, local_file_path
                FROM articles
                WHERE pmid IN ({placeholders})
                """,
                list(pmids),
            )
        else:
            cursor.execute("SELECT pmid, pmcid, source, local_file_path FROM articles")
        rows = cursor.fetchall()
        connection.close()

        synced = {"pmc": 0, "abstracts": 0}

        for row in rows:
            local_path = row["local_file_path"]
            if not local_path:
                continue

            source = Path(local_path)
            content_source = row["source"] or ""

            if content_source.startswith("pmc"):
                dest = config.UPDATED_PMC / source.name
                if self._copy_if_exists(source, dest):
                    synced["pmc"] += 1
            elif content_source == "pubmed_abstract":
                dest = config.UPDATED_ABSTRACTS / source.name
                if self._copy_if_exists(source, dest):
                    synced["abstracts"] += 1

        return synced

    def _folder_counts(self):
        def count_files(folder):
            folder = Path(folder)
            if not folder.exists():
                return 0
            return sum(1 for path in folder.iterdir() if path.is_file())

        return {
            "downloads_pmc_full_text": count_files(config.DOWNLOADS_PMC),
            "downloads_pubmed_abstracts": count_files(config.DOWNLOADS_ABSTRACTS),
            "gemini_cache_pmc_full_text": count_files(config.GEMINI_CACHE_PMC),
            "gemini_cache_pubmed_abstracts": count_files(config.GEMINI_CACHE_ABSTRACTS),
            "updated_pmc_full_text": count_files(config.UPDATED_PMC),
            "updated_pubmed_abstracts": count_files(config.UPDATED_ABSTRACTS),
        }

    def _summary_path(self, run_time=None):
        run_time = run_time or datetime.now()
        config.UPDATED_DIR.mkdir(parents=True, exist_ok=True)
        if self.frequency == "monthly":
            return config.UPDATED_DIR / f"{run_time:%Y-%m}_summary.json"
        return config.UPDATED_DIR / f"{run_time:%Y-%m-%d}_summary.json"

    def write_report(self, sync_summary, db_stats=None, db=None):
        run_time = datetime.now()
        updated_pmids = (
            sync_summary.get("new_processed", []) + sync_summary.get("modified_processed", [])
        )
        synced_files = (
            self.sync_files_to_updated(db, pmids=updated_pmids) if db and updated_pmids else {}
        )

        report = {
            "report_type": "project_update",
            "frequency": self.frequency,
            "generated_at": run_time.isoformat(),
            "sync_summary": sync_summary,
            "database_stats": db_stats or {},
            "folder_counts": self._folder_counts(),
            "files_synced_this_run": synced_files,
        }

        path = self._summary_path(run_time)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Updated folder synced; summary saved to {path}")
        return path
