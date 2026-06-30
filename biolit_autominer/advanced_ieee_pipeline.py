"""
IEEE paper pipeline: scraping + incremental updates + LLM comparison scaffold.
"""

import json
from pathlib import Path

import pandas as pd

from .config import config
from .enhanced_auto_pipeline import EnhancedAutoPipeline
from .extraction_accuracy_evaluator import ExtractionAccuracyEvaluator
from .multi_llm_extractor import MultiLLMExtractor


class AdvancedIEEEPipeline:
    def __init__(self, output_dir=None):
        self.output_dir = Path(output_dir or config.OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.scrape_pipeline = EnhancedAutoPipeline(output_dir=self.output_dir)
        self.extractor = MultiLLMExtractor()
        self.evaluator = ExtractionAccuracyEvaluator()

    def run_full_study(self, num_articles=100, search_query=None, llm_models=None):
        search_query = search_query or config.DEFAULT_SEARCH_QUERY
        llm_models = llm_models or ["gemini"]

        scrape_result = self.scrape_pipeline.full_workflow(
            search_query=search_query,
            max_results=num_articles,
            process_limit=num_articles,
            use_incremental=True,
        )

        # Placeholder LLM stage: ready for full-text text once downloader is added.
        llm_summary = {
            "models_requested": llm_models,
            "articles_scraped": scrape_result.get("processed_count", 0),
            "note": "LLM extraction runs after full-text download is implemented.",
        }

        report = {
            "search_query": search_query,
            "scraping": scrape_result,
            "llm_summary": llm_summary,
        }

        report_path = self.output_dir / "ieee_study_report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        table_path = self.output_dir / "ieee_summary_table.csv"
        pd.DataFrame(
            [
                {
                    "metric": "processed_articles",
                    "value": scrape_result.get("processed_count", 0),
                },
                {
                    "metric": "skipped_unchanged",
                    "value": scrape_result.get("skipped_count", 0),
                },
                {
                    "metric": "time_saved_pct",
                    "value": scrape_result.get("time_saved_pct", 0),
                },
                {
                    "metric": "duration_seconds",
                    "value": scrape_result.get("duration_seconds", 0),
                },
            ]
        ).to_csv(table_path, index=False)

        print(f"IEEE report saved to {report_path}")
        print(f"IEEE summary table saved to {table_path}")
        return report
