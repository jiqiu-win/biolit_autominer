"""Persist pipeline state to your own AWS S3 bucket for cloud scheduled runs."""

import os
from pathlib import Path

from .config import config

# Your bucket (NOT pmc-oa-opendata — that is PMC's read-only source bucket)
S3_BUCKET = os.getenv("BIOLIT_S3_BUCKET", "")
S3_PREFIX = os.getenv("BIOLIT_S3_PREFIX", "biolit_autominer").strip("/")


def _s3_client():
    try:
        import boto3
    except ImportError as exc:
        raise ImportError(
            "Install boto3 for cloud state sync: pip install boto3"
        ) from exc
    return boto3.client("s3")


def _enabled():
    return bool(S3_BUCKET)


def _key(rel_path):
    return f"{S3_PREFIX}/{rel_path}".replace("//", "/")


def upload_file(local_path, rel_path=None):
    """Upload one local file to your S3 bucket."""
    if not _enabled():
        return False
    local_path = Path(local_path)
    if not local_path.is_file():
        return False
    rel_path = rel_path or local_path.name
    _s3_client().upload_file(str(local_path), S3_BUCKET, _key(rel_path))
    return True


def download_file(rel_path, local_path):
    """Download one file from your S3 bucket if it exists."""
    if not _enabled():
        return False
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    client = _s3_client()
    try:
        client.download_file(S3_BUCKET, _key(rel_path), str(local_path))
        return True
    except client.exceptions.ClientError:
        return False


def restore_state():
    """
    Pull articles.db and staging manifest before a cloud run.
    Enables incremental sync across scheduled runs without your PC.
    """
    if not _enabled():
        print("Cloud state: BIOLIT_S3_BUCKET not set — starting with empty/local state.")
        return {"restored": []}

    restored = []
    targets = [
        ("articles.db", config.DATABASE_PATH),
        (
            "staging_manifest.json",
            config.PMC_STAGING_MANIFEST,
        ),
        ("sync_history.json", config.SYNC_HISTORY_PATH),
    ]
    for rel, local in targets:
        if download_file(rel, local):
            restored.append(str(local))
            print(f"Cloud state: restored {local}")
    return {"restored": restored}


def save_state():
    """Push database and daily outputs to your S3 bucket after a cloud run."""
    if not _enabled():
        print("Cloud state: BIOLIT_S3_BUCKET not set — skipping upload.")
        return {"uploaded": []}

    uploaded = []
    files = [
        (config.DATABASE_PATH, "articles.db"),
        (config.EXCEL_OUTPUT, "articles_database.xlsx"),
        (config.SYNC_HISTORY_PATH, "sync_history.json"),
        (config.PMC_STAGING_MANIFEST, "staging_manifest.json"),
    ]
    for local, rel in files:
        if upload_file(local, rel):
            uploaded.append(rel)
            print(f"Cloud state: uploaded s3://{S3_BUCKET}/{_key(rel)}")

    client = _s3_client()
    summary_dir = config.UPDATED_DIR
    if summary_dir.is_dir():
        for path in summary_dir.glob("*_summary.json"):
            rel = f"summaries/{path.name}"
            upload_file(path, rel)
            uploaded.append(rel)

    txt_dir = config.UPDATED_PMC_TXT
    if txt_dir.is_dir():
        for path in txt_dir.glob("*.txt"):
            rel = f"pmc_staging/{path.name}"
            upload_file(path, rel)
            uploaded.append(rel)

    archive_dir = config.DOWNLOADS_PMC_TXT
    if archive_dir.is_dir():
        for path in archive_dir.glob("*.txt"):
            rel = f"pmc_archive/{path.name}"
            upload_file(path, rel)
            uploaded.append(rel)

    return {"uploaded": uploaded, "bucket": S3_BUCKET, "prefix": S3_PREFIX}
