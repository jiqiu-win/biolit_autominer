import time

from .article_database import ArticleDatabase
from .config import config
from .incremental_sync import IncrementalSync
from .pubmed_scraper import FullTextDownloader, PubMedScraper


class IncrementalUpdateManager:
    """
    Decide which PubMed articles need work and skip unchanged records.

    Download priority:
        1. PMC full text (Entrez)
        2. PMC abstract-only (when full text is restricted)
        3. PubMed abstract (only when no usable PMC record)
    """

    def __init__(self, db: ArticleDatabase, sync: IncrementalSync, scraper: PubMedScraper):
        self.db = db
        self.sync = sync
        self.scraper = scraper
        self.downloader = FullTextDownloader()

    def plan_update(self, search_query, max_results=100):
        existing_hash_map = self.db.get_hash_map()
        classification = self.sync.classify_articles(
            search_query,
            existing_hash_map,
            max_results=max_results,
        )

        to_process = classification["new"] + classification["modified"]
        skipped = classification["unchanged"]
        total_found = len(classification["all_pmids"])
        time_saved_pct = (len(skipped) / total_found * 100) if total_found else 0.0

        return {
            "search_query": search_query,
            "total_found": total_found,
            "new": classification["new"],
            "modified": classification["modified"],
            "unchanged": classification["unchanged"],
            "to_process": to_process,
            "skipped_count": len(skipped),
            "time_saved_pct": round(time_saved_pct, 2),
        }

    def process_articles(self, pmids, status="new"):
        """Fetch metadata, PMCID, download text with PMC-first priority."""
        processed = []
        errors = []

        pmcid_map = self.sync.map_pmcids_batch(pmids)

        for pmid in pmids:
            metadata = self.sync.fetch_metadata(pmid)
            if metadata.get("error"):
                errors.append({"pmid": pmid, "error": metadata["error"]})
                continue

            pmcid = pmcid_map.get(pmid)
            download = self.downloader.download_article(pmid, pmcid, metadata)

            if not download.get("saved"):
                errors.append({"pmid": pmid, "error": "No text content saved"})
                continue

            # Only scrape PubMed web page when we fall back to PubMed abstract.
            if download["content_source"] == "pubmed_abstract":
                link_data = self.scraper.get_full_text_links(pmid)
            else:
                link_data = {}
            record = {
                **metadata,
                "pmcid": pmcid,
                "status": status,
                "has_full_text": download["content_source"] == "pmc_full_text",
                "source": download["content_source"],
                "local_file_path": str(download["path"]),
                "local_pdf_path": str(download["pdf_path"]) if download.get("pdf_path") else None,
                "full_text_url": link_data.get("full_text_url"),
            }
            self.db.add_article(pmid, record)
            processed.append(pmid)

        return {"processed": processed, "errors": errors}

    def run_incremental_sync(self, search_query, max_results=100, process_limit=None, include_pmids=None):
        start = time.time()
        plan = self.plan_update(search_query, max_results=max_results)

        include_pmids = [str(p) for p in (include_pmids or [])]
        remaining = [p for p in plan["to_process"] if p not in include_pmids]
        pmids_to_process = include_pmids + remaining
        if process_limit is not None:
            pmids_to_process = pmids_to_process[:process_limit]

        modified_set = set(plan["modified"])

        new_processed = []
        modified_processed = []
        all_errors = []

        for pmid in pmids_to_process:
            status = "modified" if pmid in modified_set or pmid in include_pmids else "new"
            result = self.process_articles([pmid], status=status)
            if pmid in result["processed"]:
                if status == "modified":
                    modified_processed.append(pmid)
                else:
                    new_processed.append(pmid)
            all_errors.extend(result["errors"])

        duration = round(time.time() - start, 2)
        summary = {
            "search_query": search_query,
            "total_found": plan["total_found"],
            "new_count": len(plan["new"]),
            "modified_count": len(plan["modified"]),
            "unchanged_count": len(plan["unchanged"]),
            "processed_count": len(new_processed) + len(modified_processed),
            "skipped_count": plan["skipped_count"],
            "time_saved_pct": plan["time_saved_pct"],
            "duration_seconds": duration,
            "new_processed": new_processed,
            "modified_processed": modified_processed,
            "errors": all_errors,
            "notes": (
                f"Processed {len(new_processed)} new and "
                f"{len(modified_processed)} modified articles; "
                f"skipped {plan['skipped_count']} unchanged."
            ),
        }

        self.db.log_sync(summary)
        return summary
