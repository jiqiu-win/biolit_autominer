"""Run Gemini 2.5 extraction on downloaded article text files."""

from pathlib import Path

from .article_database import ArticleDatabase
from .config import config
from .extraction_exporter import export_extraction_workbook, rows_from_gemini_text
from .multi_llm_extractor import MultiLLMExtractor
from .prompts import build_prompt


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
            candidates.append(Path(local_path))
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
            return {"pmid": row["pmid"], "status": "error", "error": "Text file not found"}

        title = row["title"] or ""
        text = text_path.read_text(encoding="utf-8")
        if not text.strip():
            return {"pmid": row["pmid"], "status": "error", "error": "Empty text file"}

        truncated = text[: config.GEMINI_MAX_TEXT_CHARS]
        result = self.extractor.extract_full_prompt(
            build_prompt(truncated, title),
        )
        if result.get("status") != "success":
            return {"pmid": row["pmid"], "status": "error", "error": result.get("error", "Gemini failed")}

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
        return {
            "pmid": row["pmid"],
            "status": "success",
            "cache_path": str(cache_path),
            "source_file": self.source_file_label(row),
        }

    def run(self, pmids=None, force=False, limit=None):
        rows = self.db.get_articles_for_extraction(pmids=pmids)
        if limit is not None:
            rows = rows[:limit]

        results = {"processed": [], "skipped": [], "errors": []}
        extraction_rows = []
        replaced_source_files = []

        for row in rows:
            outcome = self.extract_article(row, force=force)
            if outcome["status"] == "success":
                results["processed"].append(outcome["pmid"])
                replaced_source_files.append(outcome["source_file"])
                extraction_rows.extend(
                    rows_from_gemini_text(
                        outcome["source_file"],
                        Path(outcome["cache_path"]).read_text(encoding="utf-8"),
                    )
                )
            elif outcome["status"] == "skipped":
                results["skipped"].append(outcome["pmid"])
            else:
                results["errors"].append(outcome)

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
