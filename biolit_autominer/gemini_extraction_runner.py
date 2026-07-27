"""Run Gemini 2.5 extraction on downloaded article text files."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .article_database import ArticleDatabase
from .config import config
from .extraction_exporter import export_extraction_workbook, rows_from_gemini_text
from .multi_llm_extractor import MultiLLMExtractor
from .prompts import build_prompt

# Maps the Title-Case keys used by the xlsx export (rows_from_gemini_text) to the
# snake_case columns in the findings table, so a parsed row can be written to
# either destination without parsing the raw Gemini response twice with two
# different formats.
_FINDING_KEY_MAP = {
    "Tested chemical": "tested_chemical",
    "Subject type": "subject_type",
    "Basic information": "basic_information",
    "Exposure method": "exposure_method",
    "Marker": "marker",
    "Result": "result",
    "Evidence type": "evidence_type",
    "Exposure dose": "exposure_dose",
    "Exposure duration": "exposure_duration",
    "Tissue/organ": "tissue_organ",
    "Evidence sentences": "evidence_sentences",
}


def _to_db_finding(xlsx_row):
    return {db_key: xlsx_row.get(xlsx_key, "") for xlsx_key, db_key in _FINDING_KEY_MAP.items()}


def _is_empty_finding(db_finding):
    """True for the blank placeholder row rows_from_gemini_text() creates when
    Gemini legitimately returns "No results" -- meaningful as a visible row in
    the xlsx, but shouldn't become an empty row in the findings table."""
    return all(not str(value).strip() for value in db_finding.values())

# Written to disk every N completions, not just once at the very end -- so a
# job killed by a SLURM walltime limit (or anything else) still leaves a
# usable spreadsheet for whatever finished, instead of losing it all.
WORKBOOK_CHECKPOINT_EVERY = 200


class GeminiExtractionRunner:
    def __init__(self, db: ArticleDatabase):
        self.db = db
        self.extractor = MultiLLMExtractor()

    def resolve_text_path(self, row):
        pmid = row["pmid"]
        pmcid = row["pmcid"] or ""
        title = row["title"] or ""
        source = row["source"] or ""
        local_path = row["local_file_path"]

        candidates = []
        if local_path:
            candidates.append(config.resolve_project_path(local_path))
        if source == "pubmed_abstract":
            candidates.extend(
                [
                    config.updated_abstract_txt_path(pmid),
                    config.abstract_download_path(pmid),
                ]
            )
        elif source.startswith("pmc"):
            candidates.extend(
                [
                    config.updated_pmc_txt_path(pmid, pmcid, title),
                    config.pmc_download_path(pmid, pmcid, title),
                    config.DOWNLOADS_PMC / config.pmc_filename(pmid, pmcid, title),
                ]
            )

        for path in candidates:
            if path.is_file():
                return path
        return None

    def source_file_label(self, row):
        pmid = row["pmid"]
        pmcid = row["pmcid"] or ""
        title = row["title"] or ""
        source = row["source"] or ""
        if source == "pubmed_abstract":
            return config.abstract_filename(pmid)
        if source.startswith("pmc"):
            return config.pmc_filename(pmid, pmcid, title)
        return Path(row["local_file_path"]).name if row.get("local_file_path") else pmid

    def extract_article(self, row, force=False):
        if row["gemini_processed"] and not force:
            return {"pmid": row["pmid"], "status": "skipped", "reason": "already processed"}

        text_path = self.resolve_text_path(row)
        if not text_path:
            error = "Text file not found"
            self.db.mark_extraction_failed(row["pmid"], error)
            return {"pmid": row["pmid"], "status": "error", "error": error}

        title = row["title"] or ""
        text = text_path.read_text(encoding="utf-8")
        if not text.strip():
            error = "Empty text file"
            self.db.mark_extraction_failed(row["pmid"], error)
            return {"pmid": row["pmid"], "status": "error", "error": error}

        truncated = text[: config.GEMINI_MAX_TEXT_CHARS]
        result = self.extractor.extract_full_prompt(
            build_prompt(truncated, title),
        )
        if result.get("status") != "success":
            error = result.get("error", "Gemini failed")
            self.db.mark_extraction_failed(row["pmid"], error)
            return {"pmid": row["pmid"], "status": "error", "error": error}

        source = row["source"] or ""
        if source == "pubmed_abstract":
            cache_path = self.extractor.save_result(
                row["pmid"], result, source_type="pubmed_abstract", title=row["title"] or ""
            )
        else:
            cache_path = self.extractor.save_result(
                row["pmid"],
                result,
                source_type="pmc",
                pmcid=row["pmcid"],
                title=row["title"] or "",
            )

        self.db.mark_gemini_processed(row["pmid"], str(cache_path), result.get("raw_response", ""))

        source_file = self.source_file_label(row)
        parsed_rows = rows_from_gemini_text(source_file, result.get("raw_response", ""))
        for parsed in parsed_rows:
            db_finding = _to_db_finding(parsed)
            if not _is_empty_finding(db_finding):
                self.db.add_finding(row["pmid"], db_finding)

        return {
            "pmid": row["pmid"],
            "status": "success",
            "cache_path": str(cache_path),
            "source_file": source_file,
        }

    def run(self, pmids=None, force=False, limit=None, max_workers=1):
        rows = self.db.get_articles_for_extraction(pmids=pmids)
        if limit is not None:
            rows = rows[:limit]

        results = {"processed": [], "skipped": [], "errors": []}
        extraction_rows = []
        replaced_source_files = []
        since_checkpoint = 0

        def handle_outcome(outcome):
            nonlocal since_checkpoint
            if outcome["status"] == "success":
                results["processed"].append(outcome["pmid"])
                replaced_source_files.append(outcome["source_file"])
                extraction_rows.extend(
                    rows_from_gemini_text(
                        outcome["source_file"],
                        Path(outcome["cache_path"]).read_text(encoding="utf-8"),
                    )
                )
                since_checkpoint += 1
            elif outcome["status"] == "skipped":
                results["skipped"].append(outcome["pmid"])
            else:
                results["errors"].append(outcome)

            if since_checkpoint >= WORKBOOK_CHECKPOINT_EVERY:
                export_extraction_workbook(
                    extraction_rows,
                    replace_source_files=replaced_source_files if force else None,
                )
                extraction_rows.clear()
                replaced_source_files.clear()
                since_checkpoint = 0
                print(f"  checkpoint: {len(results['processed'])} processed so far")

        if max_workers <= 1:
            for row in rows:
                handle_outcome(self.extract_article(row, force=force))
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(self.extract_article, row, force) for row in rows]
                for future in as_completed(futures):
                    handle_outcome(future.result())

        if extraction_rows or replaced_source_files:
            export_extraction_workbook(
                extraction_rows,
                replace_source_files=replaced_source_files if force else None,
            )

        print(
            f"Gemini extraction: {len(results['processed'])} processed, "
            f"{len(results['skipped'])} skipped, {len(results['errors'])} errors"
        )
        return results
