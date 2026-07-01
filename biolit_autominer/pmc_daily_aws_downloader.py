"""Daily PMC full-text download via AWS Cloud Service with staging → archive workflow."""

import time

from .article_database import ArticleDatabase
from .config import config
from .incremental_sync import IncrementalSync
from .pmc_staging_manager import PmcStagingManager
from .pubmed_scraper import FullTextDownloader


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

        for pmid in to_process:
            pmcid = pmcid_map.get(pmid)
            if not pmcid:
                skipped_no_pmc.append(pmid)
                continue

            metadata = self.sync.fetch_metadata(pmid)
            if metadata.get("error"):
                errors.append({"pmid": pmid, "error": metadata["error"]})
                continue

            result = self.download_pmc_aws_first(pmid, pmcid, metadata)
            if not result.get("saved"):
                errors.append({"pmid": pmid, "error": result.get("error", "Not saved")})
                continue

            content_source = result.get("content_source", "")
            if content_source != "pmc_full_text":
                abstract_only.append(pmid)
                continue

            status = "modified" if pmid in modified_set else "new"
            record = {
                **metadata,
                "pmcid": pmcid,
                "status": status,
                "has_full_text": True,
                "source": content_source,
                "local_file_path": str(result["path"]),
                "local_pdf_path": str(result["pdf_path"]) if result.get("pdf_path") else None,
                "content_hash": ArticleDatabase.compute_content_hash(metadata),
            }
            self.db.add_article(pmid, record)
            downloaded.append(
                {
                    "pmid": pmid,
                    "pmcid": pmcid,
                    "path": str(result["path"]),
                    "source_method": result.get("source_method"),
                }
            )

        duration = round(time.time() - start, 2)
        summary = {
            "search_query": search_query,
            "total_found": len(classification["all_pmids"]),
            "archive": archive_summary,
            "downloaded_count": len(downloaded),
            "abstract_only_count": len(abstract_only),
            "skipped_no_pmc_count": len(skipped_no_pmc),
            "unchanged_count": len(classification["unchanged"]),
            "duration_seconds": duration,
            "downloaded": downloaded,
            "abstract_only": abstract_only,
            "skipped_no_pmc": skipped_no_pmc,
            "errors": errors,
            "staging_dir": str(config.UPDATED_PMC_TXT),
            "archive_dir": str(config.DOWNLOADS_PMC_TXT),
        }

        self.db.log_sync(
            {
                "search_query": search_query,
                "total_found": summary["total_found"],
                "new_count": len(classification["new"]),
                "modified_count": len(classification["modified"]),
                "unchanged_count": summary["unchanged_count"],
                "processed_count": len(downloaded),
                "skipped_count": summary["unchanged_count"],
                "time_saved_pct": round(
                    summary["unchanged_count"] / summary["total_found"] * 100, 2
                )
                if summary["total_found"]
                else 0.0,
                "duration_seconds": duration,
                "notes": (
                    f"Daily AWS PMC: {len(downloaded)} full-text staged, "
                    f"{archive_summary['moved_count']} archived."
                ),
            }
        )

        print(
            f"Daily AWS PMC download: {len(downloaded)} staged, "
            f"{archive_summary['moved_count']} archived, "
            f"{len(abstract_only)} abstract-only, "
            f"{len(errors)} errors ({duration}s)"
        )
        return summary
