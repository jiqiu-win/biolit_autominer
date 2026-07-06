"""Detect existing PMC downloads and sync files into downloaded/."""

import shutil
from pathlib import Path

from .config import config

ABSTRACT_ONLY_MARKER = "[NOTE: Full text not available in PMC Open Access"
MIN_FULLTEXT_WORDS = 150


def pmc_txt_candidates(pmid, pmcid, title=""):
    """All known locations for a PMC full-text .txt file."""
    return [
        config.updated_pmc_txt_path(pmid, pmcid, title),
        config.pmc_download_path(pmid, pmcid, title),
        config.DOWNLOADS_PMC / config.pmc_filename(pmid, pmcid, title),
    ]


def find_pmc_txt(pmid, pmcid, title=""):
    for path in pmc_txt_candidates(pmid, pmcid, title):
        if path.is_file():
            return path
    return None


def is_full_text_file(path):
    """True when file looks like PMC full text, not abstract-only."""
    path = Path(path)
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if ABSTRACT_ONLY_MARKER in text[:800]:
        return False
    return len(text.split()) >= MIN_FULLTEXT_WORDS


def _glob_pmc_txt(folder, pmid, pmcid):
    """Find a PMC txt file by PMID/PMCID prefix (title slug may differ)."""
    folder = Path(folder)
    if not folder.is_dir():
        return None
    pmcid = config.format_pmcid(pmcid)
    pattern = f"{pmcid}_{pmid}_*.txt"
    matches = sorted(folder.glob(pattern))
    for path in matches:
        if is_full_text_file(path):
            return path
    return None


def is_already_downloaded(pmid, pmcid, title="", db_row=None):
    """
    Return (downloaded: bool, path: Path|None, location: str).
    location is 'staging', 'archive', or 'legacy'.
    """
    pmcid = config.format_pmcid(pmcid) if pmcid else ""
    pmid = str(pmid)

    for label, folder in (
        ("staging", config.UPDATED_PMC_TXT),
        ("archive", config.DOWNLOADS_PMC_TXT),
        ("legacy", config.DOWNLOADS_PMC),
    ):
        path = _glob_pmc_txt(folder, pmid, pmcid)
        if path:
            return True, path, label
        exact = folder / config.pmc_filename(pmid, pmcid, title)
        if exact.is_file() and is_full_text_file(exact):
            return True, exact, label

    if db_row:
        local_path = db_row.get("local_file_path")
        if local_path:
            path = config.resolve_project_path(local_path)
            if path.is_file() and is_full_text_file(path):
                if path.parent.resolve() == config.UPDATED_PMC_TXT.resolve():
                    return True, path, "staging"
                if path.parent.resolve() == config.DOWNLOADS_PMC_TXT.resolve():
                    return True, path, "archive"
                return True, path, "legacy"

    return False, None, ""


def sync_pmc_txt_to_downloaded(source_path, pmid, pmcid, title=""):
    """
    Ensure PMC .txt exists under downloaded/pmc_full_text/txt/.
    Copies from staging if needed; leaves staging copy in place.
    """
    source_path = Path(source_path)
    dest_path = config.pmc_download_path(pmid, pmcid, title)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.is_file():
        return None

    # Keep the on-disk filename when title slug differs from DB title.
    if source_path.name.startswith(f"{config.format_pmcid(pmcid)}_{pmid}_"):
        dest_path = dest_path.parent / source_path.name

    if source_path.resolve() != dest_path.resolve():
        shutil.copy2(source_path, dest_path)

    return dest_path


def sync_pmc_pdf_to_downloaded(pmid, pmcid, title="", source_pdf=None):
    """Copy PMC PDF to downloaded/pmc_full_text/pdf/ if present."""
    dest = config.pmc_pdf_download_path(pmid, pmcid, title)
    if source_pdf:
        source_pdf = Path(source_pdf)
        if source_pdf.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            if source_pdf.resolve() != dest.resolve():
                shutil.copy2(source_pdf, dest)
            return dest

    staging_pdf = config.UPDATED_PMC_PDF / config.pmc_pdf_filename(pmid, pmcid, title)
    if staging_pdf.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staging_pdf, dest)
        return dest
    return None


def organize_existing_download(pmid, pmcid, title, db=None, source_path=None):
    """
    For an already-downloaded article: copy txt/pdf into downloaded/ and
    update DB path to archive location.
    """
    pmcid = config.format_pmcid(pmcid) if pmcid else ""
    row = db.get_article(pmid) if db else None
    if source_path is None:
        _, source_path, _ = is_already_downloaded(
            pmid, pmcid, title or (row or {}).get("title", ""), db_row=row
        )

    resolved_title = title or (row or {}).get("title") or ""
    if not source_path:
        return None

    archive_txt = sync_pmc_txt_to_downloaded(source_path, pmid, pmcid, resolved_title)
    if archive_txt is None and source_path.is_file():
        dest_path = config.pmc_download_path(pmid, pmcid, resolved_title)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.resolve() != dest_path.resolve():
            shutil.copy2(source_path, dest_path)
        archive_txt = dest_path
    pdf_path = None
    if row and row.get("local_pdf_path"):
        pdf_path = sync_pmc_pdf_to_downloaded(
            pmid, pmcid, resolved_title, source_pdf=row["local_pdf_path"]
        )
    else:
        pdf_path = sync_pmc_pdf_to_downloaded(pmid, pmcid, resolved_title)

    if db and archive_txt:
        db.update_local_file_path(
            pmid,
            str(archive_txt),
            pdf_path=str(pdf_path) if pdf_path else None,
        )

    return archive_txt
