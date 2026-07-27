import os
import socket
from pathlib import Path

from dotenv import load_dotenv

from .file_formatter import title_slug
from .prompts import (
    BATCH_SIZE,
    EXCLUDE_TYPES,
    MAX_RESULTS,
    RETMAX_FETCH,
    SEARCH_QUERY,
)

# Project root: biolit_autominer/ (one level above this package folder)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# A stalled network connection (e.g. PubMed) otherwise hangs forever -- Python's
# default socket timeout is None (no timeout at all). BioPython's Entrez calls
# don't expose a timeout parameter directly, so this is set globally, once, for
# every plain-socket-based call in the process (Entrez, boto3, requests without
# their own explicit timeout, etc.) rather than patching each call site.
# NOTE: this does NOT cover vertexai's generate_content() -- that runs over
# gRPC, which ignores socket.setdefaulttimeout(). It needs its own
# request_options={"timeout": ...} passed at each call site (see
# multi_llm_extractor.py and chain_of_thought_pipeline.py).
socket.setdefaulttimeout(60)


class Config:
    NCBI_EMAIL = os.getenv("NCBI_EMAIL", "jq2430@columbia.edu")
    NCBI_API_KEY = os.getenv("NCBI_API_KEY")
    NCBI_SLEEP_TIME = 0.1 if NCBI_API_KEY else 0.34

    GEMINI_PROJECT_ID = os.getenv("GEMINI_PROJECT_ID", "rs-vertexai-czhu")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_TEMPERATURE = 0.0

    # Pipeline outputs (inside auto_pipeline_output/)
    OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(BASE_DIR / "auto_pipeline_output")))
    UPDATED_DIR = OUTPUT_DIR / "updated"
    UPDATED_PMC = UPDATED_DIR / "PMC_full_text_updated"
    UPDATED_PMC_TXT = UPDATED_PMC / "txt"
    UPDATED_PMC_PDF = UPDATED_PMC / "pdf"
    UPDATED_ABSTRACTS = UPDATED_DIR / "Pubmed_abstracts_updated"
    UPDATED_ABSTRACTS_TXT = UPDATED_ABSTRACTS / "txt"
    UPDATED_ABSTRACTS_PDF = UPDATED_ABSTRACTS / "pdf"

    DATABASE_PATH = OUTPUT_DIR / "articles.db"
    EXCEL_OUTPUT = OUTPUT_DIR / "articles_database.xlsx"
    SYNC_HISTORY_PATH = OUTPUT_DIR / "sync_history.json"

    # Raw downloads (outside auto_pipeline_output/, project root)
    DOWNLOADS_DIR = Path(os.getenv("DOWNLOADS_DIR", str(BASE_DIR / "downloaded")))
    DOWNLOADS_PMC = DOWNLOADS_DIR / "pmc_full_text"
    DOWNLOADS_PMC_TXT = DOWNLOADS_PMC / "txt"
    DOWNLOADS_PMC_PDF = DOWNLOADS_PMC / "pdf"
    DOWNLOADS_ABSTRACTS = DOWNLOADS_DIR / "pubmed_abstracts"

    # Gemini 2.5 extractions (outside auto_pipeline_output/, project root)
    GEMINI_CACHE_DIR = Path(os.getenv("GEMINI_CACHE_DIR", str(BASE_DIR / "gemini_raw_cache")))
    GEMINI_CACHE_PMC = GEMINI_CACHE_DIR / "PMC_full_text"
    GEMINI_CACHE_ABSTRACTS = GEMINI_CACHE_DIR / "Pubmed_abstracts"

    UPDATED_EXTRACTION_XLSX = UPDATED_DIR / "full_text_extraction.xlsx"

    # Conference / PI-facing dataset (updated daily)
    DATASET_DB_PATH = OUTPUT_DIR / "biolit_dataset.db"
    DATASET_XLSX_PATH = UPDATED_DIR / "biolit_dataset.xlsx"
    DATASET_FINDINGS_CSV = UPDATED_DIR / "biolit_findings.csv"
    DATASET_ARTICLES_CSV = UPDATED_DIR / "biolit_articles.csv"

    CHEAP_LLM_MODEL = os.getenv("CHEAP_LLM_MODEL", "deepseek")
    STRONG_LLM_MODEL = os.getenv("STRONG_LLM_MODEL", "gemini")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    QWEN_API_KEY = os.getenv("QWEN_API_KEY")
    QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")

    UPDATE_FREQUENCY = os.getenv("UPDATE_FREQUENCY", "daily")

    # Legacy aliases
    RAW_TEXT_CACHE = DOWNLOADS_DIR
    GEMINI_CACHE = GEMINI_CACHE_DIR

    DEFAULT_SEARCH_QUERY = os.getenv("SEARCH_QUERY") or SEARCH_QUERY
    BATCH_SIZE = BATCH_SIZE
    MAX_RESULTS = MAX_RESULTS
    RETMAX_FETCH = RETMAX_FETCH
    EXCLUDE_PUBLICATION_TYPES = EXCLUDE_TYPES
    GEMINI_MAX_TEXT_CHARS = int(os.getenv("GEMINI_MAX_TEXT_CHARS", "50000"))

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # PMC official text-mining AWS Cloud Service (no account required)
    PMC_AWS_BUCKET = os.getenv("PMC_AWS_BUCKET", "pmc-oa-opendata")
    PMC_AWS_HTTPS_BASE = os.getenv(
        "PMC_AWS_HTTPS_BASE",
        f"https://{os.getenv('PMC_AWS_BUCKET', 'pmc-oa-opendata')}.s3.amazonaws.com",
    )

    # PMC full-text staging: updated/.../txt first, then downloaded/.../txt after N days
    PMC_STAGING_MANIFEST = UPDATED_PMC_TXT / ".staging_manifest.json"
    PMC_STAGING_AGE_DAYS = int(os.getenv("PMC_STAGING_AGE_DAYS", "1"))
    # Recommended cron time (informational — set in crontab/LaunchAgent yourself)
    PMC_DAILY_RUN_TIME = os.getenv("PMC_DAILY_RUN_TIME", "09:00")

    @classmethod
    def setup(cls):
        folders = [
            cls.OUTPUT_DIR,
            cls.UPDATED_PMC,
            cls.UPDATED_PMC_TXT,
            cls.UPDATED_PMC_PDF,
            cls.UPDATED_ABSTRACTS,
            cls.UPDATED_ABSTRACTS_TXT,
            cls.UPDATED_ABSTRACTS_PDF,
            cls.DOWNLOADS_PMC,
            cls.DOWNLOADS_PMC_TXT,
            cls.DOWNLOADS_PMC_PDF,
            cls.DOWNLOADS_ABSTRACTS,
            cls.GEMINI_CACHE_PMC,
            cls.GEMINI_CACHE_ABSTRACTS,
        ]
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)
        print("Configuration validated")

    # Publication types that must never enter the dataset (reviews, editorials, etc.).
    # Built from EXCLUDE_TYPES in prompts.py, normalised for case-insensitive matching.
    EXCLUDED_PUB_TYPES = {t.lower() for t in EXCLUDE_TYPES} | {
        "systematic review",
        "review article",
        "retracted publication",
        "published erratum",
    }

    @classmethod
    def is_excluded_publication_type(cls, publication_types):
        """True if any of an article's PubMed publication types is excluded."""
        for pub_type in publication_types or []:
            if str(pub_type).strip().lower() in cls.EXCLUDED_PUB_TYPES:
                return True
        return False

    @staticmethod
    def format_pmcid(pmcid):
        pmcid = str(pmcid).strip()
        if not pmcid:
            return pmcid
        return pmcid if pmcid.upper().startswith("PMC") else f"PMC{pmcid}"

    @classmethod
    def pmc_filename(cls, pmid, pmcid, title=""):
        slug = title_slug(title) if title else "Untitled"
        return f"{cls.format_pmcid(pmcid)}_{pmid}_{slug}.txt"

    @classmethod
    def pmc_pdf_filename(cls, pmid, pmcid, title=""):
        slug = title_slug(title) if title else "Untitled"
        return f"{cls.format_pmcid(pmcid)}_{pmid}_{slug}.pdf"

    @classmethod
    def abstract_filename(cls, pmid):
        return f"PM{pmid}_abstract.txt"

    @classmethod
    def resolve_project_path(cls, path):
        """Resolve relative paths against project BASE_DIR."""
        path = Path(path)
        if path.is_absolute():
            return path
        return BASE_DIR / path

    @classmethod
    def pmc_download_path(cls, pmid, pmcid, title=""):
        """Archived PMC full-text path (after staging period)."""
        return cls.DOWNLOADS_PMC_TXT / cls.pmc_filename(pmid, pmcid, title)

    @classmethod
    def pmc_staging_path(cls, pmid, pmcid, title=""):
        """Fresh PMC full-text path (day 0 staging in updated/)."""
        return cls.updated_pmc_txt_path(pmid, pmcid, title)

    @classmethod
    def abstract_download_path(cls, pmid):
        return cls.DOWNLOADS_ABSTRACTS / cls.abstract_filename(pmid)

    @classmethod
    def pmc_pdf_download_path(cls, pmid, pmcid, title=""):
        return cls.DOWNLOADS_PMC_PDF / cls.pmc_pdf_filename(pmid, pmcid, title)

    @classmethod
    def pmc_gemini_path(cls, pmid, pmcid, title=""):
        return cls.GEMINI_CACHE_PMC / cls.pmc_filename(pmid, pmcid, title)

    @classmethod
    def abstract_gemini_path(cls, pmid):
        return cls.GEMINI_CACHE_ABSTRACTS / cls.abstract_filename(pmid)

    @classmethod
    def updated_pmc_txt_path(cls, pmid, pmcid, title=""):
        return cls.UPDATED_PMC_TXT / cls.pmc_filename(pmid, pmcid, title)

    @classmethod
    def updated_pmc_pdf_path(cls, pmid, pmcid, title=""):
        return cls.UPDATED_PMC_PDF / cls.pmc_pdf_filename(pmid, pmcid, title)

    @classmethod
    def updated_abstract_txt_path(cls, pmid):
        return cls.UPDATED_ABSTRACTS_TXT / cls.abstract_filename(pmid)

    @classmethod
    def updated_pmc_path(cls, pmid, pmcid, title=""):
        return cls.updated_pmc_txt_path(pmid, pmcid, title)

    @classmethod
    def updated_abstract_path(cls, pmid):
        return cls.updated_abstract_txt_path(pmid)


config = Config
