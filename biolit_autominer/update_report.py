"""
Sync incrementally updated files into auto_pipeline_output/updated/.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

from .config import config
from .extraction_exporter import build_rows_from_cache, export_extraction_workbook
from .pmc_staging_manager import PmcStagingManager


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

    def _resolve_abstract_source(self, pmid, local_path):
        if local_path and Path(local_path).is_file():
            return Path(local_path)

        candidates = [
            config.abstract_download_path(pmid),
            config.DOWNLOADS_ABSTRACTS / f"PMID{pmid}_*.txt",
        ]
        direct = candidates[0]
        if direct.is_file():
            return direct

        legacy_matches = sorted(config.DOWNLOADS_ABSTRACTS.glob(f"PMID{pmid}_*.txt"))
        if legacy_matches:
            return legacy_matches[0]

        updated_legacy = sorted(config.UPDATED_ABSTRACTS_TXT.glob(f"PMID{pmid}_*.txt"))
        if updated_legacy:
            return updated_legacy[0]

        updated_legacy = sorted(config.UPDATED_ABSTRACTS.glob(f"PMID{pmid}_*.txt"))
        if updated_legacy:
            return updated_legacy[0]

        return None

    def migrate_legacy_filenames(self, db):
        """Rename PMID{pmid}_Title.txt downloads to PM{pmid}_abstract.txt."""
        import sqlite3

        connection = sqlite3.connect(db.db_path)
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT pmid, source, local_file_path
            FROM articles
            WHERE source = 'pubmed_abstract'
            """
        )
        rows = cursor.fetchall()
        migrated = 0

        for row in rows:
            pmid = row["pmid"]
            local_path = self._resolve_abstract_source(pmid, row["local_file_path"])
            if not local_path:
                continue

            new_path = config.abstract_download_path(pmid)
            if local_path.resolve() == new_path.resolve() and local_path.name == new_path.name:
                cursor.execute(
                    "UPDATE articles SET local_file_path = ? WHERE pmid = ?",
                    (str(new_path), pmid),
                )
                continue

            new_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, new_path)
            if local_path.resolve() != new_path.resolve():
                local_path.unlink(missing_ok=True)
            cursor.execute(
                "UPDATE articles SET local_file_path = ? WHERE pmid = ?",
                (str(new_path), pmid),
            )
            migrated += 1

        connection.commit()
        connection.close()

        for stale in config.UPDATED_ABSTRACTS.glob("PMID*.txt"):
            stale.unlink(missing_ok=True)
        for stale in config.UPDATED_ABSTRACTS_TXT.glob("PMID*.txt"):
            stale.unlink(missing_ok=True)

        return migrated

    def _move_flat_files_to_txt_subfolders(self):
        """Move legacy flat files in updated/ into txt/ subfolders."""
        moved = 0
        for folder, txt_folder in (
            (config.UPDATED_PMC, config.UPDATED_PMC_TXT),
            (config.UPDATED_ABSTRACTS, config.UPDATED_ABSTRACTS_TXT),
        ):
            if not folder.exists():
                continue
            for path in folder.iterdir():
                if path.is_file() and path.suffix.lower() == ".txt":
                    dest = txt_folder / path.name
                    txt_folder.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, dest)
                    path.unlink(missing_ok=True)
                    moved += 1
        return moved

    def sync_files_to_updated(self, db, pmids=None):
        import sqlite3

        connection = sqlite3.connect(db.db_path)
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        if pmids:
            placeholders = ",".join("?" for _ in pmids)
            cursor.execute(
                f"""
                SELECT pmid, pmcid, title, source, local_file_path, local_pdf_path
                FROM articles
                WHERE pmid IN ({placeholders})
                """,
                list(pmids),
            )
        else:
            cursor.execute(
                """
                SELECT pmid, pmcid, title, source, local_file_path, local_pdf_path
                FROM articles
                """
            )
        rows = cursor.fetchall()
        connection.close()

        synced = {"pmc_txt": 0, "pmc_pdf": 0, "abstracts_txt": 0, "abstracts_pdf": 0}

        for row in rows:
            local_path = row["local_file_path"]
            local_pdf_path = row["local_pdf_path"]
            if not local_path and not local_pdf_path:
                continue

            pmid = row["pmid"]
            pmcid = row["pmcid"] or ""
            title = row["title"] or ""
            content_source = row["source"] or ""

            if content_source.startswith("pmc"):
                if local_path:
                    source = Path(local_path)
                    if source.is_file():
                        dest = config.updated_pmc_txt_path(pmid, pmcid, title)
                        if source.resolve() == dest.resolve():
                            synced["pmc_txt"] += 1
                        elif self._copy_if_exists(source, dest):
                            synced["pmc_txt"] += 1
                if local_pdf_path:
                    pdf_source = Path(local_pdf_path)
                    if pdf_source.is_file():
                        dest = config.updated_pmc_pdf_path(pmid, pmcid, title)
                        if self._copy_if_exists(pdf_source, dest):
                            synced["pmc_pdf"] += 1
            elif content_source == "pubmed_abstract":
                if local_path:
                    source = Path(local_path)
                    if source.is_file():
                        dest = config.updated_abstract_txt_path(pmid)
                        if self._copy_if_exists(source, dest):
                            synced["abstracts_txt"] += 1
                if local_pdf_path:
                    pdf_source = Path(local_pdf_path)
                    if pdf_source.is_file():
                        dest = config.UPDATED_ABSTRACTS_PDF / pdf_source.name
                        if self._copy_if_exists(pdf_source, dest):
                            synced["abstracts_pdf"] += 1

        return synced

    def sync_extraction_workbook(self, db, pmids=None):
        import sqlite3

        connection = sqlite3.connect(db.db_path)
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        if pmids:
            placeholders = ",".join("?" for _ in pmids)
            cursor.execute(
                f"""
                SELECT pmid, pmcid, title, source
                FROM articles
                WHERE pmid IN ({placeholders})
                """,
                list(pmids),
            )
        else:
            cursor.execute("SELECT pmid, pmcid, title, source FROM articles")
        rows = cursor.fetchall()
        connection.close()

        extraction_rows = []
        cot_dir = config.GEMINI_CACHE_DIR / "chain_of_thought"

        for row in rows:
            pmid = row["pmid"]
            pmcid = row["pmcid"] or ""
            title = row["title"] or ""
            content_source = row["source"] or ""

            if content_source == "pubmed_abstract":
                source_file = config.abstract_filename(pmid)
                gemini_path = config.abstract_gemini_path(pmid)
                cot_path = cot_dir / f"PM{pmid}_abstract_chain_of_thought.txt"
            elif content_source.startswith("pmc"):
                source_file = config.pmc_filename(pmid, pmcid, title)
                gemini_path = config.pmc_gemini_path(pmid, pmcid, title)
                cot_path = cot_dir / f"{Path(source_file).stem}_chain_of_thought.txt"
            else:
                continue

            extraction_rows.extend(
                build_rows_from_cache(source_file, gemini_path, cot_path)
            )

        if extraction_rows:
            export_extraction_workbook(extraction_rows)
        elif not config.UPDATED_EXTRACTION_XLSX.is_file():
            export_extraction_workbook([])
        return len(extraction_rows)

    def _folder_counts(self):
        def count_files(folder):
            folder = Path(folder)
            if not folder.exists():
                return 0
            return sum(1 for path in folder.rglob("*") if path.is_file())

        return {
            "downloads_pmc_full_text": count_files(config.DOWNLOADS_PMC_TXT),
            "downloads_pmc_staging": count_files(config.UPDATED_PMC_TXT),
            "downloads_pubmed_abstracts": count_files(config.DOWNLOADS_ABSTRACTS),
            "gemini_cache_pmc_full_text": count_files(config.GEMINI_CACHE_PMC),
            "gemini_cache_pubmed_abstracts": count_files(config.GEMINI_CACHE_ABSTRACTS),
            "updated_pmc_txt": count_files(config.UPDATED_PMC_TXT),
            "updated_pmc_pdf": count_files(config.UPDATED_PMC_PDF),
            "updated_pubmed_abstracts_txt": count_files(config.UPDATED_ABSTRACTS_TXT),
            "updated_pubmed_abstracts_pdf": count_files(config.UPDATED_ABSTRACTS_PDF),
            "updated_extraction_xlsx": 1 if config.UPDATED_EXTRACTION_XLSX.is_file() else 0,
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
        migrated = self.migrate_legacy_filenames(db) if db else 0
        moved_flat = self._move_flat_files_to_txt_subfolders()
        archived = PmcStagingManager.migrate_flat_downloads_to_txt_subfolder()
        archive_summary = (
            PmcStagingManager().archive_staged_files(db=db) if db else {"moved_count": 0}
        )
        synced_files = self.sync_files_to_updated(db) if db else {}
        extraction_rows = self.sync_extraction_workbook(db) if db else 0

        report = {
            "report_type": "project_update",
            "frequency": self.frequency,
            "generated_at": run_time.isoformat(),
            "sync_summary": sync_summary,
            "database_stats": db_stats or {},
            "folder_counts": self._folder_counts(),
            "files_synced_this_run": synced_files,
            "legacy_files_migrated": migrated,
            "flat_files_moved_to_txt": moved_flat,
            "legacy_downloads_migrated_to_txt": archived,
            "pmc_staging_archived": archive_summary,
            "extraction_rows_added": extraction_rows,
        }

        path = self._summary_path(run_time)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Updated folder synced; summary saved to {path}")
        return path

    def write_daily_aws_report(self, daily_summary, db_stats=None, db=None):
        """Write YYYY-MM-DD_summary.json for the daily AWS PMC downloader."""
        run_time = datetime.now()
        migrated = self.migrate_legacy_filenames(db) if db else 0
        archived = PmcStagingManager.migrate_flat_downloads_to_txt_subfolder()
        archive_summary = daily_summary.get("archive") or {"moved_count": 0}

        report = {
            "report_type": "daily_pmc_aws",
            "frequency": self.frequency,
            "scheduled_run_time": config.PMC_DAILY_RUN_TIME,
            "generated_at": run_time.isoformat(),
            "timing": daily_summary.get("timing", {}),
            "diagnosis": daily_summary.get("diagnosis", {}),
            "aws_service_reachable": daily_summary.get("aws_service_reachable"),
            "sync_summary": {
                "search_query": daily_summary.get("search_query"),
                "total_found": daily_summary.get("total_found"),
                "new_count": daily_summary.get("new_count"),
                "modified_count": daily_summary.get("modified_count"),
                "unchanged_count": daily_summary.get("unchanged_count"),
                "processed_count": daily_summary.get("downloaded_count"),
                "downloaded_count": daily_summary.get("downloaded_count"),
                "abstract_only_count": daily_summary.get("abstract_only_count"),
                "skipped_no_pmc_count": daily_summary.get("skipped_no_pmc_count"),
                "duration_seconds": daily_summary.get("duration_seconds"),
                "downloaded": daily_summary.get("downloaded", []),
                "abstract_only": daily_summary.get("abstract_only", []),
                "errors": daily_summary.get("errors", []),
                "notes": daily_summary.get("diagnosis", {}).get("user_message", ""),
            },
            "article_diagnoses": daily_summary.get("article_diagnoses", []),
            "database_stats": db_stats or {},
            "folder_counts": self._folder_counts(),
            "pmc_staging_archived": archive_summary,
            "legacy_files_migrated": migrated,
            "legacy_downloads_migrated_to_txt": archived,
            "excel_path": str(config.EXCEL_OUTPUT),
        }

        path = self._summary_path(run_time)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Daily summary saved to {path}")
        return path
