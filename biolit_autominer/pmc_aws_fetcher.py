"""Fetch PMC full text via official PMC text-mining services (AWS Cloud Service, BioC API).

Per PMC policy, automated retrieval must use only:
  - PMC Cloud Service (AWS S3: pmc-oa-opendata)
  - E-Utilities (handled in pubmed_scraper.fetch_pmc_article)
  - BioC API
  - PMC FTP / OAI-PMH (not used here)

See: https://pmc.ncbi.nlm.nih.gov/tools/textmining/
     https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/
"""

import json
import re
import time

import requests

from .config import config

S3_BUCKET = "pmc-oa-opendata"
S3_HTTPS_BASE = f"https://{S3_BUCKET}.s3.amazonaws.com"
BIOC_BASE = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi"

LEGACY_TXT_PREFIXES = (
    "deprecated/oa_comm/txt/all",
    "deprecated/oa_noncomm/txt/all",
    "deprecated/phe_timebound/txt/all",
    "deprecated/author_manuscript/txt/all",
)

LEGACY_XML_PREFIXES = (
    "deprecated/oa_comm/xml/all",
    "deprecated/oa_noncomm/xml/all",
    "deprecated/phe_timebound/xml/all",
    "deprecated/author_manuscript/xml/all",
)

BIOC_SKIP_SECTIONS = {"REF", "FIG", "TABLE", "SUPPL", "AUTH_CONT", "COMP_INT"}


class PMCAwsFetcher:
    """Retrieve licensed PMC full text from AWS Cloud Service and BioC API."""

    MIN_FULLTEXT_WORDS = 150

    def __init__(self, sleep_time=None, parse_pmc_xml=None):
        self.sleep_time = sleep_time if sleep_time is not None else config.NCBI_SLEEP_TIME
        self.parse_pmc_xml = parse_pmc_xml
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "BiolitAutoMiner/1.0 (research; mailto:jq2430@columbia.edu)",
            }
        )

    def _pause(self):
        time.sleep(self.sleep_time)

    @staticmethod
    def _s3_url_to_https(s3_url):
        if not s3_url:
            return None
        key = s3_url.replace(f"s3://{S3_BUCKET}/", "").split("?")[0]
        return f"{S3_HTTPS_BASE}/{key}"

    @staticmethod
    def _https_key(key):
        return f"{S3_HTTPS_BASE}/{key.lstrip('/')}"

    def _get_bytes(self, url):
        try:
            response = self.session.get(url, timeout=90)
        except requests.RequestException:
            return None
        self._pause()
        if response.status_code == 200:
            return response.content
        return None

    def _head_exists(self, url):
        try:
            response = self.session.head(url, timeout=30)
        except requests.RequestException:
            return False
        self._pause()
        return response.status_code == 200

    def list_article_versions(self, pmcid):
        pmcid = config.format_pmcid(pmcid)
        list_url = (
            f"{S3_HTTPS_BASE}/?list-type=2&prefix={pmcid}.&delimiter=/"
        )
        try:
            response = self.session.get(list_url, timeout=30)
        except requests.RequestException:
            return []
        self._pause()
        if response.status_code != 200:
            return []

        versions = []
        for match in re.finditer(rf"<Prefix>{re.escape(pmcid)}\.(\d+)/</Prefix>", response.text):
            versions.append(int(match.group(1)))
        return sorted(versions)

    def fetch_metadata(self, pmcid, version):
        pmcid = config.format_pmcid(pmcid)
        url = self._https_key(f"metadata/{pmcid}.{version}.json")
        content = self._get_bytes(url)
        if not content:
            return None
        try:
            return json.loads(content)
        except Exception:
            return None

    @classmethod
    def extract_body_from_aws_txt(cls, txt_content):
        text = txt_content.decode("utf-8", errors="replace") if isinstance(txt_content, bytes) else txt_content
        lines = text.splitlines()

        start_idx = 0
        for idx, line in enumerate(lines):
            if re.match(r"^\d+\.\s+\S", line.strip()):
                start_idx = idx
                break

        body = "\n".join(lines[start_idx:]).strip()
        if not body:
            body = text.strip()
        return body

    @staticmethod
    def extract_body_from_bioc(data):
        if not data:
            return "", ""

        root = data[0] if isinstance(data, list) else data
        documents = root.get("documents") or []
        if not documents:
            return "", ""

        doc = documents[0]
        title = ""
        parts = []
        for passage in doc.get("passages", []):
            infons = passage.get("infons") or {}
            section = (infons.get("section_type") or infons.get("type") or "").upper()
            text = (passage.get("text") or "").strip()
            if not text:
                continue
            if section == "TITLE" and not title:
                title = text
                continue
            if section in BIOC_SKIP_SECTIONS:
                continue
            if section.startswith("H") or section in {"INTRO", "METHODS", "RESULTS", "DISCUSS", "CONCL", "ABSTRACT"}:
                parts.append(f"## {text}" if section in {"INTRO", "METHODS", "RESULTS", "DISCUSS", "CONCL"} else text)
            else:
                parts.append(text)

        return title, "\n\n".join(parts)

    def _parse_with_xml(self, xml_bytes):
        if not self.parse_pmc_xml or not xml_bytes:
            return None
        try:
            return self.parse_pmc_xml(xml_bytes)
        except Exception:
            return None

    def _fetch_legacy_object(self, pmcid, prefixes, suffix):
        pmcid = config.format_pmcid(pmcid)
        for prefix in prefixes:
            url = self._https_key(f"{prefix}/{pmcid}.{suffix}")
            content = self._get_bytes(url)
            if content:
                return content, url
        return None, None

    def _fetch_from_metadata(self, metadata, min_words):
        title = metadata.get("title") or ""
        license_code = metadata.get("license_code")

        xml_url = self._s3_url_to_https(metadata.get("xml_url"))
        if xml_url:
            xml_bytes = self._get_bytes(xml_url)
            parsed = self._parse_with_xml(xml_bytes)
            if parsed and parsed.get("is_full_text") and len(parsed.get("body", "").split()) >= min_words:
                parsed["source_method"] = "pmc_aws_xml"
                parsed["license_code"] = license_code
                pdf_bytes, pdf_url = self._fetch_pdf_from_metadata(metadata)
                if pdf_bytes:
                    parsed["pdf_bytes"] = pdf_bytes
                    parsed["pdf_url"] = pdf_url
                    parsed["pdf_source"] = "pmc_aws"
                return parsed

        text_url = self._s3_url_to_https(metadata.get("text_url"))
        if text_url:
            txt_bytes = self._get_bytes(text_url)
            if txt_bytes:
                body = self.extract_body_from_aws_txt(txt_bytes)
                if len(body.split()) >= min_words:
                    result = {
                        "title": title,
                        "abstract": "",
                        "body": body,
                        "is_full_text": True,
                        "source_method": "pmc_aws_txt",
                        "license_code": license_code,
                    }
                    pdf_bytes, pdf_url = self._fetch_pdf_from_metadata(metadata)
                    if pdf_bytes:
                        result["pdf_bytes"] = pdf_bytes
                        result["pdf_url"] = pdf_url
                        result["pdf_source"] = "pmc_aws"
                    return result

        pdf_bytes, pdf_url = self._fetch_pdf_from_metadata(metadata)
        if pdf_bytes:
            body = self._extract_pdf_text(pdf_bytes)
            if len(body.split()) >= min_words:
                return {
                    "title": title,
                    "abstract": "",
                    "body": body,
                    "is_full_text": True,
                    "source_method": "pmc_aws_pdf",
                    "license_code": license_code,
                    "pdf_bytes": pdf_bytes,
                    "pdf_url": pdf_url,
                    "pdf_source": "pmc_aws",
                }

        return None

    def _fetch_pdf_from_metadata(self, metadata):
        pdf_url = self._s3_url_to_https(metadata.get("pdf_url"))
        if not pdf_url:
            return None, None
        pdf_bytes = self._get_bytes(pdf_url)
        if pdf_bytes and pdf_bytes[:4] == b"%PDF":
            return pdf_bytes, pdf_url
        return None, None

    @staticmethod
    def _extract_pdf_text(pdf_bytes):
        try:
            import fitz
        except ImportError:
            return ""

        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = [page.get_text("text").strip() for page in document if page.get_text("text").strip()]
        return "\n\n".join(pages)

    def _fetch_legacy(self, pmcid, min_words):
        pmcid = config.format_pmcid(pmcid)

        xml_bytes, _ = self._fetch_legacy_object(pmcid, LEGACY_XML_PREFIXES, "xml")
        parsed = self._parse_with_xml(xml_bytes)
        if parsed and parsed.get("is_full_text") and len(parsed.get("body", "").split()) >= min_words:
            parsed["source_method"] = "pmc_aws_legacy_xml"
            return parsed

        txt_bytes, _ = self._fetch_legacy_object(pmcid, LEGACY_TXT_PREFIXES, "txt")
        if txt_bytes:
            body = self.extract_body_from_aws_txt(txt_bytes)
            if len(body.split()) >= min_words:
                return {
                    "title": "",
                    "abstract": "",
                    "body": body,
                    "is_full_text": True,
                    "source_method": "pmc_aws_legacy_txt",
                }

        return None

    def _fetch_bioc(self, pmcid, min_words):
        pmcid = config.format_pmcid(pmcid)
        url = f"{BIOC_BASE}/BioC_json/{pmcid}/unicode"
        try:
            response = self.session.get(url, timeout=90)
        except requests.RequestException:
            return None
        self._pause()
        if response.status_code != 200:
            return None
        if response.text.lstrip().startswith("[Error]"):
            return None

        try:
            data = response.json()
        except Exception:
            return None

        title, body = self.extract_body_from_bioc(data)
        if len(body.split()) >= min_words:
            return {
                "title": title,
                "abstract": "",
                "body": body,
                "is_full_text": True,
                "source_method": "pmc_bioc",
            }
        return None

    def fetch_full_text_fallback(self, pmcid, min_words=None):
        """
        Try official PMC text-mining sources when Entrez XML is abstract-only.

        Order:
        1. AWS Cloud Service (latest article version: metadata → XML → TXT → PDF)
        2. AWS legacy deprecated paths (until Aug 2026)
        3. BioC API

        Returns dict compatible with FullTextDownloader.save_pmc_file().
        """
        min_words = min_words if min_words is not None else self.MIN_FULLTEXT_WORDS
        pmcid = config.format_pmcid(pmcid)

        versions = self.list_article_versions(pmcid)
        for version in reversed(versions):
            metadata = self.fetch_metadata(pmcid, version)
            if not metadata:
                continue
            result = self._fetch_from_metadata(metadata, min_words)
            if result:
                return result

        legacy = self._fetch_legacy(pmcid, min_words)
        if legacy:
            return legacy

        bioc = self._fetch_bioc(pmcid, min_words)
        if bioc:
            return bioc

        return {"is_full_text": False, "title": "", "abstract": "", "body": ""}

    def check_availability(self, pmcid):
        """
        Check whether a PMCID is in the licensed AWS text-mining bucket.
        Used to distinguish PMC dataset limits from pipeline errors.
        """
        pmcid = config.format_pmcid(pmcid)
        versions = self.list_article_versions(pmcid)
        if versions:
            metadata = self.fetch_metadata(pmcid, versions[-1])
            return {
                "pmcid": pmcid,
                "in_aws_bucket": True,
                "versions": versions,
                "license_code": (metadata or {}).get("license_code"),
                "latest_version": versions[-1],
            }

        for prefix in LEGACY_TXT_PREFIXES:
            url = self._https_key(f"{prefix}/{pmcid}.txt")
            if self._head_exists(url):
                return {
                    "pmcid": pmcid,
                    "in_aws_bucket": True,
                    "versions": [],
                    "license_code": None,
                    "latest_version": None,
                    "legacy_path": prefix,
                }

        return {
            "pmcid": pmcid,
            "in_aws_bucket": False,
            "versions": [],
            "license_code": None,
            "latest_version": None,
        }

    @staticmethod
    def check_aws_service_health():
        """Return True if the PMC AWS bucket responds."""
        try:
            response = requests.get(
                f"{S3_HTTPS_BASE}/?list-type=2&max-keys=1",
                timeout=15,
                headers={"User-Agent": "BiolitAutoMiner/1.0 (health-check)"},
            )
            return response.status_code == 200
        except requests.RequestException:
            return False
