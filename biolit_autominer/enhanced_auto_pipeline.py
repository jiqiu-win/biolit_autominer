from pathlib import Path

from .article_database import ArticleDatabase
from .config import config
from .incremental_sync import IncrementalSync
from .incremental_update_manager import IncrementalUpdateManager
from .pubmed_scraper import PubMedScraper
from .gemini_extraction_runner import GeminiExtractionRunner
from .update_report import UpdateReportWriter


class EnhancedAutoPipeline:
    """Main orchestrator for PubMed scraping and incremental updates."""

    def __init__(self, email=None, api_key=None, gemini_project_id=None, output_dir=None):
        self.email = email or config.NCBI_EMAIL
        self.api_key = api_key or config.NCBI_API_KEY
        self.gemini_project_id = gemini_project_id or config.GEMINI_PROJECT_ID
        self.output_dir = Path(output_dir or config.OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.db = ArticleDatabase(self.output_dir / "articles.db")
        self.scraper = PubMedScraper()
        self.sync = IncrementalSync(self.email, self.api_key)
        self.update_manager = IncrementalUpdateManager(self.db, self.sync, self.scraper)

    def full_workflow(
        self,
        search_query=None,
        max_results=100,
        process_limit=10,
        use_incremental=True,
        include_pmids=None,
        run_gemini=True,
        gemini_limit=None,
    ):
        search_query = search_query or config.DEFAULT_SEARCH_QUERY
        print(f"Starting workflow: {search_query}")

        if use_incremental:
            summary = self.update_manager.run_incremental_sync(
                search_query=search_query,
                max_results=max_results,
                process_limit=process_limit,
                include_pmids=include_pmids,
            )
        else:
            summary = self._simple_workflow(search_query, process_limit)

        processed_pmids = summary.get("new_processed", []) + summary.get("modified_processed", [])
        gemini_summary = {}
        if run_gemini:
            gemini_runner = GeminiExtractionRunner(self.db)
            gemini_summary = gemini_runner.run(
                pmids=processed_pmids or None,
                limit=gemini_limit,
            )
            summary["gemini_extraction"] = gemini_summary

        self.db.export_to_excel(self.output_dir / "articles_database.xlsx")
        self.db.export_sync_history(self.output_dir / "sync_history.json")

        report_writer = UpdateReportWriter(output_dir=self.output_dir)
        report_writer.write_report(
            sync_summary=summary,
            db_stats=self.db.get_stats(),
            db=self.db,
        )

        self.db.print_stats()

        return {
            "status": "completed",
            **summary,
        }

    def _simple_workflow(self, search_query, process_limit):
        """Original non-incremental path kept for quick tests."""
        existing_pmids = self.db.get_existing_pmids()
        new_pmids = self.sync.get_new_articles(search_query, existing_pmids)
        selected = new_pmids[:process_limit]

        result = self.update_manager.process_articles(selected, status="new")
        return {
            "search_query": search_query,
            "total_found": len(new_pmids),
            "new_count": len(new_pmids),
            "modified_count": 0,
            "unchanged_count": 0,
            "processed_count": len(result["processed"]),
            "skipped_count": 0,
            "time_saved_pct": 0.0,
            "duration_seconds": 0.0,
            "errors": result["errors"],
        }
