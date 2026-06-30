"""Extract full text from PMC HTML pages when Entrez XML is abstract-only."""

import re
import time

import requests
from bs4 import BeautifulSoup

from .config import config


class PMCHtmlFetcher:
    """Fetch and parse PMC article HTML (fallback when XML API is restricted)."""

    MIN_PAGE_BYTES = 100_000
    MAX_RETRIES = 5
    BROWSER_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self, sleep_time=None):
        self.sleep_time = sleep_time if sleep_time is not None else config.NCBI_SLEEP_TIME
        self.session = requests.Session()
        self.session.headers.update(self.BROWSER_HEADERS)

    def _pause(self):
        time.sleep(self.sleep_time)

    def fetch_article_page(self, pmcid):
        pmcid = config.format_pmcid(pmcid)
        url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"

        for attempt in range(self.MAX_RETRIES):
            response = self.session.get(url, timeout=60)
            self._pause()
            if len(response.text) >= self.MIN_PAGE_BYTES:
                return {"url": url, "html": response.text, "soup": BeautifulSoup(response.text, "html.parser")}
            time.sleep(self.sleep_time * (attempt + 1))

        return {"url": url, "html": response.text, "soup": BeautifulSoup(response.text, "html.parser")}

    @staticmethod
    def find_pdf_url(soup, pmcid):
        meta = soup.find("meta", attrs={"name": "citation_pdf_url"})
        if meta and meta.get("content"):
            return meta["content"].strip()

        match = re.search(
            rf"https://pmc\.ncbi\.nlm\.nih\.gov/articles/{re.escape(pmcid)}/pdf/[^\"'\s>]+\.pdf",
            str(soup),
        )
        return match.group(0) if match else None

    def download_pdf(self, pdf_url, referer):
        response = self.session.get(pdf_url, timeout=90, headers={"Referer": referer})
        self._pause()
        if response.status_code == 200 and response.content[:4] == b"%PDF":
            return response.content
        return None

    @staticmethod
    def extract_text_from_pdf(pdf_bytes):
        try:
            import fitz
        except ImportError as exc:
            raise ImportError("Install pymupdf to extract text from PMC PDFs: pip install pymupdf") from exc

        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = [page.get_text("text").strip() for page in document if page.get_text("text").strip()]
        return "\n\n".join(pages)

    @staticmethod
    def extract_body_from_html(soup):
        article = soup.find("article")
        if article is None:
            return ""

        body_section = article.select_one("section.main-article-body") or article.select_one(
            "section.body"
        )
        root = body_section or article

        for tag in root.select("script, style, nav, .ref-list"):
            tag.decompose()

        skip_headings = {
            "PERMALINK",
            "Figures",
            "References",
            "Acknowledgments",
            "Acknowledgements",
        }
        parts = []
        seen = set()

        for element in root.find_all(["h2", "h3", "h4", "h5", "p"]):
            if element.find_parent("section", class_="front-matter"):
                continue
            if element.find_parent("section", class_="ref-list"):
                continue

            text = element.get_text(" ", strip=True)
            if not text or text in seen:
                continue

            if element.name.startswith("h"):
                if text in skip_headings:
                    continue
                parts.append(f"## {text}")
            else:
                parts.append(text)
            seen.add(text)

        return "\n\n".join(parts)

    def fetch_full_text_fallback(self, pmcid, min_words=150):
        """
        Try PMC HTML page, then PMC PDF linked from that page.

        Returns dict compatible with FullTextDownloader.save_pmc_file().
        """
        page = self.fetch_article_page(pmcid)
        soup = page["soup"]
        title_node = soup.find("meta", attrs={"name": "citation_title"})
        title = title_node["content"].strip() if title_node and title_node.get("content") else ""

        pdf_url = self.find_pdf_url(soup, config.format_pmcid(pmcid))
        if pdf_url:
            pdf_bytes = self.download_pdf(pdf_url, page["url"])
            if pdf_bytes:
                body = self.extract_text_from_pdf(pdf_bytes)
                if len(body.split()) >= min_words:
                    return {
                        "title": title,
                        "abstract": "",
                        "body": body,
                        "is_full_text": True,
                        "source_method": "pmc_pdf",
                    }

        body = self.extract_body_from_html(soup)
        if len(body.split()) >= min_words:
            return {
                "title": title,
                "abstract": "",
                "body": body,
                "is_full_text": True,
                "source_method": "pmc_html",
            }

        return {"is_full_text": False, "title": title, "abstract": "", "body": body}
