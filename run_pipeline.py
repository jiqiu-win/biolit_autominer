"""
Run the Biolit AutoMiner pipeline from the command line.

Example:
    python run_pipeline.py --num_articles 10
    python run_pipeline.py --num_articles 100 --max_results 100
"""

import argparse

from biolit_autominer.config import config
from biolit_autominer.enhanced_auto_pipeline import EnhancedAutoPipeline


def main():
    parser = argparse.ArgumentParser(description="Run the Biolit AutoMiner pipeline")
    parser.add_argument(
        "--query",
        default=config.DEFAULT_SEARCH_QUERY,
        help="PubMed search query",
    )
    parser.add_argument(
        "--num_articles",
        type=int,
        default=10,
        help="How many new/modified articles to process this run",
    )
    parser.add_argument(
        "--max_results",
        type=int,
        default=100,
        help="Maximum PubMed IDs to inspect per search",
    )
    parser.add_argument(
        "--output_dir",
        default=str(config.OUTPUT_DIR),
        help="Folder for database, Excel, and sync history",
    )
    parser.add_argument(
        "--no_incremental",
        action="store_true",
        help="Disable incremental update logic (process only brand-new PMIDs)",
    )
    args = parser.parse_args()

    config.setup()

    pipeline = EnhancedAutoPipeline(output_dir=args.output_dir)
    result = pipeline.full_workflow(
        search_query=args.query,
        max_results=args.max_results,
        process_limit=args.num_articles,
        use_incremental=not args.no_incremental,
    )

    print("\nRun complete:")
    print(f"  Processed: {result.get('processed_count', 0)}")
    print(f"  Skipped unchanged: {result.get('skipped_count', 0)}")
    print(f"  Time saved: {result.get('time_saved_pct', 0)}%")
    print(f"  Duration: {result.get('duration_seconds', 0)} seconds")


if __name__ == "__main__":
    main()
