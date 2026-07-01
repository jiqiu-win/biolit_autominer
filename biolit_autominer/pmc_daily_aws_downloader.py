"""Daily PMC full-text download via AWS Cloud Service with staging → archive workflow."""

import time

from .article_database import ArticleDatabase
from .config import config
from .incremental_sync import IncrementalSync
from .pmc_aws_fetcher import PMCAwsFetcher
from .pmc_download_diagnosis import build_run_diagnosis, classify_article_outcome
from .pmc_staging_manager import PmcStagingManager
from .pubmed_scraper import FullTextDownloader
from .update_report import UpdateReportWriter


class PmcDailyAwsDownloader:
    """
    Each daily run:
      1. Archive staging files older than PMC_STAGING_AGE_DAYS (default 1 day)
      2. Search PubMed for new/modified articles
      3. Download PMC full text (AWS first, then Entrez/BioC fallbacks)
      4. Save new .txt files to updated/PMC_full_text_updated/txt/
    """

    def __init__(self, db=None, sync=None, staging=None):
        self.db = db or ArticleDatabase(config.DATABASE_PATH)
        self.sync = sync or IncrementalSync()
        self.downloader = FullTextDownloader()
        self.staging = staging or PmcStagingManager()

    def download_pmc_aws_first(self, pmid, pmcid, metadata):
        """Try AWS Cloud Service before Entrez for PMC full text."""
        title = metadata.get("title", "")
        abstract = metadata.get("abstract", "")

        aws_data = self.downloader.aws_fetcher.fetch_full_text_fallback(pmcid)
        if aws_data.get("is_full_text"):
            merged = {
                **aws_data,
                "title": title or aws_data.get("title") or "",
                "is_full_text": True,
            }
            return self.downloader.save_pmc_file(pmid, pmcid, title, abstract, merged)

        entrez_data = self.downloader.fetch_pmc_article(pmcid)
        if not entrez_data.get("error") and entrez_data.get("is_full_text"):
            return self.downloader.save_pmc_file(pmid, pmcid, title, abstract, entrez_data)

        if not entrez_data.get("error"):
            return self.downloader.save_pmc_file(pmid, pmcid, title, abstract, entrez_data)

        return {"saved": False, "error": entrez_data.get("error", "PMC download failed")}

    def run_daily(
        self,
        search_query=None,
        max_results=100,
        process_limit=None,
        include_pmids=None,
    ):
        start = time.time()
        search_query = search_query or config.DEFAULT_SEARCH_QUERY

        PmcStagingManager.migrate_flat_downloads_to_txt_subfolder()
        archive_summary = self.staging.archive_staged_files(db=self.db)

        existing_hash_map = self.db.get_hash_map()
        classification = self.sync.classify_articles(
            search_query,
            existing_hash_map,
            max_results=max_results,
        )

        include_pmids = [str(p) for p in (include_pmids or [])]
        to_process = include_pmids + [
            p for p in classification["new"] + classification["modified"] if p not in include_pmids
        ]
        if process_limit is not None:
            to_process = to_process[:process_limit]

        pmcid_map = self.sync.map_pmcids_batch(to_process) if to_process else {}
        modified_set = set(classification["modified"]) | set(include_pmids)

        downloaded = []
        skipped_no_pmc = []
        abstract_only = []
        errors = []
        article_diagnoses = []

        aws_reachable = PMCAwsFetcher.check_aws_service_health()

        for pmid in to_process:
            pmcid = pmcid_map.get(pmid)
            if not pmcid:
                diag = classify_article_outcome(pmid, None, {}, None)
                skipped_no_pmc.append({"pmid": pmid, **diag})
                article_diagnoses.append({"pmid": pmid, **diag})
                continue

            metadata = self.sync.fetch_metadata(pmid)
            if metadata.get("error"):
                err = metadata["error"]
                diag = classify_article_outcome(pmid, pmcid, {}, None, error=err)
                errors.append({"pmid": pmid, "pmcid": pmcid, "error": err, **diag})
                article_diagnoses.append({"pmid": pmid, "pmcid": pmcid, **diag})
                continue

            availability = self.downloader.aws_fetcher.check_availability(pmcid)
            result = self.download_pmc_aws_first(pmid, pmcid, metadata)
            if not result.get("saved"):
                err = result.get("error", "Not saved")
                diag = classify_article_outcome(pmid, pmcid, availability, None, error=err)
                errors.append({"pmid": pmid, "pmcid": pmcid, "error": err, **diag})
                article_diagnoses.append({"pmid": pmid, "pmcid": pmcid, **diag})
                continue

            content_source = result.get("content_source", "")
            status = "modified" if pmid in modified_set else "new"
            diag = classify_article_outcome(pmid, pmcid, availability, content_source)

            if content_source != "pmc_full_text":
                record = {
                    **metadata,
                    "pmcid": pmcid,
                    "status": status,
                    "has_full_text": False,
                    "source": content_source,
                    "local_file_path": str(result["path"]),
                    "local_pdf_path": str(result["pdf_path"]) if result.get("pdf_path") else None,
                    "content_hash": ArticleDatabase.compute_content_hash(metadata),
                    "error_message": diag["user_message"],
                }
                self.db.add_article(pmid, record)
                abstract_only.append(
                    {
                        "pmid": pmid,
                        "pmcid": pmcid,
                        "title": metadata.get("title", ""),
                        "in_aws_bucket": availability.get("in_aws_bucket"),
                        **diag,
                    }
                )
                article_diagnoses.append(
                    {"pmid": pmid, "pmcid": pmcid, "title": metadata.get("title", ""), **diag}
                )
                continue

            record = {
                **metadata,
                "pmcid": pmcid,
                "status": status,
                "has_full_text": True,
                "source": content_source,
                "local_file_path": str(result["path"]),
                "local_pdf_path": str(result["pdf_path"]) if result.get("pdf_path") else None,
                "content_hash": ArticleDatabase.compute_content_hash(metadata),
                "error_message": None,
            }
            self.db.add_article(pmid, record)
            downloaded.append(
                {
                    "pmid": pmid,
                    "pmcid": pmcid,
                    "path": str(result["path"]),
                    "source_method": result.get("source_method"),
                    **diag,
                }
            )
            article_diagnoses.append(
                {"pmid": pmid, "pmcid": pmcid, "title": metadata.get("title", ""), **diag}
            )

        duration = round(time.time() - start, 2)
        run_diagnosis = build_run_diagnosis(
            classification=classification,
            downloaded=downloaded,
            abstract_only=abstract_only,
            skipped_no_pmc=skipped_no_pmc,
            errors=errors,
            aws_reachable=aws_reachable,
            to_process_count=len(to_process),
        )

        summary = {
            "search_query": search_query,
            "total_found": len(classification["all_pmids"]),
            "new_count": len(classification["new"]),
            "modified_count": len(classification["modified"]),
            "unchanged_count": len(classification["unchanged"]),
            "archive": archive_summary,
            "downloaded_count": len(downloaded),
            "abstract_only_count": len(abstract_only),
            "skipped_no_pmc_count": len(skipped_no_pmc),
            "duration_seconds": duration,
            "downloaded": downloaded,
            "abstract_only": abstract_only,
            "skipped_no_pmc": skipped_no_pmc,
            "errors": errors,
            "article_diagnoses": article_diagnoses,
            "diagnosis": run_diagnosis,
            "timing": {
                "scheduled_run_time": config.PMC_DAILY_RUN_TIME,
                "staging_visible_immediately": True,
                "archive_after_days": config.PMC_STAGING_AGE_DAYS,
                "note": (
                    "New .txt files appear in updated/PMC_full_text_updated/txt/ immediately "
                    f"after each run. They move to downloaded/pmc_full_text/txt/ after "
                    f"{config.PMC_STAGING_AGE_DAYS} day(s). "
                    f"Set cron to {config.PMC_DAILY_RUN_TIME} daily if you want a fixed schedule."
                ),
            },
            "staging_dir": str(config.UPDATED_PMC_TXT),
            "archive_dir": str(config.DOWNLOADS_PMC_TXT),
            "aws_service_reachable": aws_reachable,
        }

        self.db.log_sync(
            {
                "search_query": search_query,
                "total_found": summary["total_found"],
                "new_count": summary["new_count"],
                "modified_count": summary["modified_count"],
                "unchanged_count": summary["unchanged_count"],
                "processed_count": len(downloaded),
                "skipped_count": summary["unchanged_count"],
                "time_saved_pct": round(
                    summary["unchanged_count"] / summary["total_found"] * 100, 2
                )
                if summary["total_found"]
                else 0.0,
                "duration_seconds": duration,
                "notes": run_diagnosis["user_message"],
            }
        )

        self.db.export_to_excel(config.EXCEL_OUTPUT)
        self.db.export_sync_history(config.SYNC_HISTORY_PATH)

        report_path = UpdateReportWriter().write_daily_aws_report(
            summary,
            db_stats=self.db.get_stats(),
            db=self.db,
        )
        summary["summary_json_path"] = str(report_path)
        summary["excel_path"] = str(config.EXCEL_OUTPUT)

        print(run_diagnosis["user_message"])
        print(
            f"Daily AWS PMC: {len(downloaded)} staged, "
            f"{archive_summary['moved_count']} archived, "
            f"{len(abstract_only)} abstract-only, "
            f"{len(errors)} errors ({duration}s)"
        )
        print(f"Summary: {report_path}")
        print(f"Excel:   {config.EXCEL_OUTPUT}")
        return summary
