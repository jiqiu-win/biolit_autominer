import time
import xml.etree.ElementTree as ET

from Bio import Entrez

from .config import config
from .file_formatter import (
    format_pmc_abstract_only_file,
    format_pmc_fulltext_file,
    format_pubmed_abstract_file,
)
from .pmc_aws_fetcher import PMCAwsFetcher
from .pmc_staging_manager import PmcStagingManager


class FullTextDownloader:
    """
    Download PMC full text via Entrez when available.

    Priority: PMC full text > PMC abstract-only > PubMed abstract.
    """

    ABSTRACT_ONLY_NOTE = (
        "[NOTE: Full text not available in PMC Open Access / Author Manuscript datasets. "
        "Abstract only. Automated retrieval is limited to PMC Cloud Service, E-Utilities, "
        "BioC API, FTP, and OAI-PMH per PMC text mining policy.]"
    )
    MIN_FULLTEXT_WORDS = 150

    def __init__(self, email=None, api_key=None, sleep_time=None):
        self.email = email or config.NCBI_EMAIL
        self.api_key = api_key or config.NCBI_API_KEY
        self.sleep_time = sleep_time if sleep_time is not None else config.NCBI_SLEEP_TIME
        self.aws_fetcher = PMCAwsFetcher(
            sleep_time=self.sleep_time,
            parse_pmc_xml=self._parse_pmc_xml,
        )
        self.staging = PmcStagingManager()
        Entrez.email = self.email
        if self.api_key:
            Entrez.api_key = self.api_key

    def _pause(self):
        time.sleep(self.sleep_time)

    @staticmethod
    def _text(node):
        if node is None:
            return ""
        return " ".join("".join(node.itertext()).split())

    @staticmethod
    def _pmc_numeric_id(pmcid):
        pmcid = config.format_pmcid(pmcid)
        return pmcid[3:] if pmcid.upper().startswith("PMC") else pmcid

    def fetch_pmc_article(self, pmcid, retries=3):
        pmc_numeric = self._pmc_numeric_id(pmcid)
        for attempt in range(retries):
            try:
                handle = Entrez.efetch(
                    db="pmc",
                    id=pmc_numeric,
                    rettype="full",
                    retmode="xml",
                )
                xml_data = handle.read()
                handle.close()
                self._pause()
                return self._parse_pmc_xml(xml_data)
            except Exception as exc:
                if attempt == retries - 1:
                    return {"error": str(exc)}
                time.sleep(self.sleep_time * (attempt + 2))
        return {"error": "Unknown PMC fetch failure"}

    def _parse_pmc_xml(self, xml_data):
        root = ET.fromstring(xml_data)
        title = self._text(root.find(".//article-title"))
        abstract_node = root.find(".//abstract")
        body_node = root.find(".//body")
        abstract = self._section_paragraphs(abstract_node)
        body = self._body_text(body_node)

        abstract_words = len(abstract.split())
        body_words = len(body.split())

        if body_words >= self.MIN_FULLTEXT_WORDS and body_words > abstract_words + 50:
            return {
                "title": title,
                "abstract": abstract,
                "body": body,
                "is_full_text": True,
            }

        fallback_abstract = abstract or body
        return {
            "title": title,
            "abstract": fallback_abstract,
            "body": body,
            "is_full_text": False,
        }

    def _section_paragraphs(self, section):
        if section is None:
            return ""
        paragraphs = [self._text(p) for p in section.findall(".//p")]
        paragraphs = [p for p in paragraphs if p]
        return "\n\n".join(paragraphs) if paragraphs else self._text(section)

    def _body_text(self, body_node):
        if body_node is None:
            return ""
        parts = []
        for sec in body_node.findall(".//sec"):
            heading = self._text(sec.find("title"))
            paragraphs = [self._text(p) for p in sec.findall(".//p")]
            paragraphs = [p for p in paragraphs if p]
            section_text = "\n\n".join(paragraphs)
            if heading and section_text:
                parts.append(f"## {heading}\n\n{section_text}")
            elif heading:
                parts.append(f"## {heading}")
            elif section_text:
                parts.append(section_text)

        if parts:
            return "\n\n".join(parts)

        paragraphs = [self._text(p) for p in body_node.findall(".//p")]
        paragraphs = [p for p in paragraphs if p]
        return "\n\n".join(paragraphs)

    @staticmethod
    def pmc_filename(pmid, pmcid, title):
        return config.pmc_filename(pmid, pmcid, title)

    @staticmethod
    def pubmed_filename(pmid, title=None):
        return config.abstract_filename(pmid)

    def save_pmc_file(self, pmid, pmcid, title, abstract, pmc_data):
        resolved_title = title or pmc_data.get("title") or ""

        if pmc_data.get("is_full_text"):
            path = config.pmc_staging_path(pmid, pmcid, resolved_title)
            content = format_pmc_fulltext_file(
                resolved_title,
                pmc_data.get("body", ""),
            )
            content_source = "pmc_full_text"
        else:
            path = config.pmc_staging_path(pmid, pmcid, resolved_title)
            content = format_pmc_abstract_only_file(
                resolved_title,
                pmc_data.get("abstract") or abstract or "",
            )
            content_source = "pmc_abstract_only"

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        if pmc_data.get("is_full_text"):
            self.staging.record_staged_file(path, pmid, pmcid, resolved_title)

        pdf_path = None
        pdf_bytes = pmc_data.get("pdf_bytes")
        if pdf_bytes:
            pdf_path = config.pmc_pdf_download_path(pmid, pmcid, resolved_title)
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(pdf_bytes)

        return {
            "path": path,
            "pdf_path": pdf_path,
            "content_source": content_source,
            "source_method": pmc_data.get("source_method"),
            "saved": True,
        }

    def save_pubmed_abstract_file(self, pmid, title, abstract):
        path = config.abstract_download_path(pmid)
        content = format_pubmed_abstract_file(title, abstract)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {
            "path": path,
            "content_source": "pubmed_abstract",
            "saved": bool(abstract),
        }

    def download_article(self, pmid, pmcid, metadata):
        """
        PMC-first download strategy.

        Order:
        1. Entrez PMC XML (E-Utilities)
        2. PMC AWS Cloud Service (XML / TXT / PDF from pmc-oa-opendata)
        3. BioC API (official fallback)
        4. PubMed abstract (only if no PMC record)
        """
        title = metadata.get("title", "")
        abstract = metadata.get("abstract", "")

        if pmcid:
            pmc_data = self.fetch_pmc_article(pmcid)
            if not pmc_data.get("error") and pmc_data.get("is_full_text"):
                return self.save_pmc_file(pmid, pmcid, title, abstract, pmc_data)

            if not pmc_data.get("error"):
                fallback = self.aws_fetcher.fetch_full_text_fallback(pmcid)
                if fallback.get("is_full_text"):
                    merged = {
                        **pmc_data,
                        **fallback,
                        "title": title or fallback.get("title") or pmc_data.get("title", ""),
                        "is_full_text": True,
                    }
                    return self.save_pmc_file(pmid, pmcid, title, abstract, merged)

                return self.save_pmc_file(pmid, pmcid, title, abstract, pmc_data)

        return self.save_pubmed_abstract_file(pmid, title, abstract)


class PubMedScraper:
    """Polite PubMed web scraper with rate limiting and robots.txt checks."""

    ROBOTS_URL = "https://pubmed.ncbi.nlm.nih.gov/robots.txt"
    BASE_URL = "https://pubmed.ncbi.nlm.nih.gov/"

    def __init__(self, sleep_time=None):
        self.sleep_time = sleep_time if sleep_time is not None else config.NCBI_SLEEP_TIME
        self.headers = {
            "User-Agent": "BiolitAutoMiner/1.0 (research; mailto:jq2430@columbia.edu)"
        }
        self._robots = None
        self._robots_loaded = False

    def _ensure_robots(self):
        if self._robots_loaded:
            return
        from urllib.robotparser import RobotFileParser

        self._robots = RobotFileParser()
        try:
            self._robots.set_url(self.ROBOTS_URL)
            self._robots.read()
        except Exception:
            pass
        self._robots_loaded = True

    def _can_fetch(self, url):
        self._ensure_robots()
        try:
            return self._robots.can_fetch(self.headers["User-Agent"], url)
        except Exception:
            return True

    def _pause(self):
        time.sleep(self.sleep_time)

    def get_full_text_links(self, pmid):
        from urllib.parse import urljoin

        import requests
        from bs4 import BeautifulSoup

        url = urljoin(self.BASE_URL, f"{pmid}/")
        if not self._can_fetch(url):
            return {
                "pmid": pmid,
                "has_full_text_link": False,
                "links": [],
                "error": "Blocked by robots.txt",
            }

        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            self._pause()

            if response.status_code != 200:
                return {"pmid": pmid, "has_full_text_link": False, "links": []}

            soup = BeautifulSoup(response.content, "html.parser")
            links = []

            for link in soup.find_all("a", class_="full-text-links-list__link"):
                href = link.get("href", "")
                links.append(
                    {
                        "text": link.get_text(strip=True),
                        "url": href,
                        "publisher": self._identify_publisher(href),
                    }
                )

            primary_url = links[0]["url"] if links else None
            return {
                "pmid": pmid,
                "has_full_text_link": bool(links),
                "links": links,
                "full_text_url": primary_url,
                "source": links[0]["publisher"] if links else None,
            }
        except Exception as exc:
            return {"pmid": pmid, "has_full_text_link": False, "error": str(exc)}

    def batch_get_links(self, pmids):
        return [self.get_full_text_links(pmid) for pmid in pmids]

    @staticmethod
    def _identify_publisher(url):
        publishers = [
            "elsevier",
            "springer",
            "wiley",
            "nature",
            "science",
            "plos",
            "pmc",
            "nih",
        ]
        url_lower = (url or "").lower()
        for publisher in publishers:
            if publisher in url_lower:
                return publisher
        return "unknown"
