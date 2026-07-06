"""
Cloud entry point: restore state → daily AWS PMC download → save state to your S3.

Use this on AWS Lambda, GitHub Actions, or any server — not on your sleeping Mac.

Requires environment variables:
  NCBI_EMAIL, NCBI_API_KEY (optional but recommended)
  BIOLIT_S3_BUCKET=your-bucket-name
  BIOLIT_S3_PREFIX=biolit_autominer   (optional)

Usage:
  python scripts/run_daily_pmc_aws_cloud.py
  python scripts/run_daily_pmc_aws_cloud.py --num_articles 50
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from biolit_autominer.article_database import ArticleDatabase
from biolit_autominer.cloud_state import restore_state, save_state
from biolit_autominer.config import config
from biolit_autominer.pmc_daily_aws_downloader import PmcDailyAwsDownloader
from biolit_autominer.pmc_staging_manager import PmcStagingManager


def main():
    parser = argparse.ArgumentParser(description="Cloud daily PMC AWS download with S3 state")
    parser.add_argument("--num_articles", type=int, default=50)
    parser.add_argument("--max_results", type=int, default=200)
    parser.add_argument("--query", default=None)
    parser.add_argument(
        "--include_pmids",
        nargs="+",
        default=[],
    )
    parser.add_argument("--no-gemini", action="store_true")
    parser.add_argument("--gemini-force", action="store_true")
    args = parser.parse_args()

    config.setup()
    restore_state()

    db = ArticleDatabase(config.DATABASE_PATH)
    downloader = PmcDailyAwsDownloader(db=db, staging=PmcStagingManager())
    summary = downloader.run_daily(
        search_query=args.query or config.DEFAULT_SEARCH_QUERY,
        max_results=args.max_results,
        process_limit=args.num_articles,
        include_pmids=args.include_pmids,
        run_gemini=not args.no_gemini,
        gemini_force=args.gemini_force,
    )

    upload = save_state()
    summary["cloud_upload"] = upload

    print("\nCloud run complete.")
    print(f"Diagnosis: {summary.get('diagnosis', {}).get('user_message')}")
    if upload.get("bucket"):
        print(f"State saved to s3://{upload['bucket']}/{upload.get('prefix')}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
