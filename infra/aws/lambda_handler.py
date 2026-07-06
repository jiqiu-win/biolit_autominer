"""AWS Lambda handler for scheduled daily PMC download."""

import json
import os
import sys
from pathlib import Path

# Lambda package root = project root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biolit_autominer.cloud_state import restore_state, save_state
from biolit_autominer.config import config
from biolit_autominer.pmc_daily_aws_downloader import PmcDailyAwsDownloader
from biolit_autominer.pmc_staging_manager import PmcStagingManager
from biolit_autominer.article_database import ArticleDatabase


def handler(event, context):
    """
    Triggered by EventBridge schedule (e.g. daily 00:01 UTC).

    Environment variables on the Lambda function:
      NCBI_EMAIL, NCBI_API_KEY
      BIOLIT_S3_BUCKET, BIOLIT_S3_PREFIX
    """
    config.setup()
    restore_state()

    db = ArticleDatabase(config.DATABASE_PATH)
    limit = int(os.getenv("PMC_DAILY_LIMIT", "50"))
    max_results = int(os.getenv("PMC_MAX_RESULTS", "200"))

    summary = PmcDailyAwsDownloader(db=db, staging=PmcStagingManager()).run_daily(
        max_results=max_results,
        process_limit=limit,
    )
    upload = save_state()

    body = {
        "diagnosis": summary.get("diagnosis"),
        "downloaded_count": summary.get("downloaded_count"),
        "cloud_upload": upload,
    }
    return {"statusCode": 200, "body": json.dumps(body)}
