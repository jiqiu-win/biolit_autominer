import hashlib
import time
import xml.etree.ElementTree as ET

from Bio import Entrez

from .config import config


class IncrementalSync:
    """PubMed search, metadata fetch, and incremental change detection."""

    def __init__(self, email=None, api_key=None, sleep_time=None):
        self.email = email or config.NCBI_EMAIL
        self.api_key = api_key or config.NCBI_API_KEY
        self.sleep_time = sleep_time if sleep_time is not None else config.NCBI_SLEEP_TIME
        Entrez.email = self.email
        if self.api_key:
            Entrez.api_key = self.api_key

    def _pause(self):
        time.sleep(self.sleep_time)

    def search_pubmed(self, query, max_results=100):
        try:
            handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results)
            result = Entrez.read(handle)
            handle.close()
            self._pause()
            return result.get("IdList", [])
        except Exception as exc:
            print(f"Search failed: {exc}")
            return []

    def fetch_metadata(self, pmid, retries=3):
        """Fetch title, authors, journal, date, and abstract from PubMed."""
        for attempt in range(retries):
            try:
                handle = Entrez.efetch(
                    db="pubmed",
                    id=pmid,
                    rettype="xml",
                    retmode="xml",
                )
                xml_data = handle.read()
                handle.close()
                self._pause()

                root = ET.fromstring(xml_data)
                article = root.find(".//PubmedArticle")
                if article is None:
                    return {"pmid": pmid}

                medline = article.find(".//MedlineCitation")
                article_node = medline.find("Article") if medline is not None else None
                if article_node is None:
                    return {"pmid": pmid}

                title = self._text(article_node.find("ArticleTitle"))
                journal = self._text(article_node.find(".//Journal/Title"))
                pub_date = self._format_pub_date(article_node.find(".//Journal/JournalIssue/PubDate"))
                abstract = self._extract_abstract(article_node.find("Abstract"))
                authors = self._extract_authors(article_node.find("AuthorList"))

                metadata = {
                    "pmid": pmid,
                    "title": title,
                    "authors": authors,
                    "journal": journal,
                    "pub_date": pub_date,
                    "abstract": abstract,
                }
                metadata["content_hash"] = self.compute_content_hash(metadata)
                return metadata
            except Exception as exc:
                if attempt == retries - 1:
                    print(f"Metadata fetch failed for PMID {pmid}: {exc}")
                    return {"pmid": pmid, "error": str(exc)}
                time.sleep(self.sleep_time * (attempt + 2))

    def fetch_metadata_batch(self, pmids):
        return [self.fetch_metadata(pmid) for pmid in pmids]

    def map_pmid_to_pmcid(self, pmid, retries=3):
        for attempt in range(retries):
            try:
                handle = Entrez.elink(dbfrom="pubmed", db="pmc", id=pmid)
                result = Entrez.read(handle)
                handle.close()
                self._pause()

                link_sets = result[0].get("LinkSetDb") or []
                if link_sets:
                    return link_sets[0]["Link"][0]["Id"]
                return None
            except Exception as exc:
                if attempt == retries - 1:
                    print(f"PMID to PMCID mapping failed for {pmid}: {exc}")
                    return None
                time.sleep(self.sleep_time * (attempt + 2))

    def map_pmcids_batch(self, pmids):
        return {pmid: self.map_pmid_to_pmcid(pmid) for pmid in pmids}

    @staticmethod
    def compute_content_hash(metadata):
        parts = [
            metadata.get("title") or "",
            metadata.get("authors") or "",
            metadata.get("journal") or "",
            metadata.get("pub_date") or "",
            metadata.get("abstract") or "",
        ]
        payload = "|".join(parts).strip().lower()
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def classify_articles(self, query, existing_hash_map, max_results=100):
        """
        Compare PubMed results with the local database.

        Returns:
            dict with keys: all_pmids, new, modified, unchanged
        """
        all_pmids = self.search_pubmed(query, max_results)
        new_pmids = []
        modified_pmids = []
        unchanged_pmids = []

        for pmid in all_pmids:
            if pmid not in existing_hash_map:
                new_pmids.append(pmid)
                continue

            old_hash = existing_hash_map.get(pmid)
            if not old_hash:
                # Backfill metadata for older records that pre-date hash tracking.
                modified_pmids.append(pmid)
                continue

            metadata = self.fetch_metadata(pmid)
            new_hash = metadata.get("content_hash")

            if new_hash and new_hash != old_hash:
                modified_pmids.append(pmid)
            else:
                unchanged_pmids.append(pmid)

        return {
            "all_pmids": all_pmids,
            "new": new_pmids,
            "modified": modified_pmids,
            "unchanged": unchanged_pmids,
        }

    def get_new_articles(self, query, existing_pmids, max_results=100):
        """Backward-compatible helper used by older code paths."""
        all_pmids = self.search_pubmed(query, max_results)
        return [pmid for pmid in all_pmids if pmid not in existing_pmids]

    @staticmethod
    def _text(node):
        if node is None:
            return ""
        return "".join(node.itertext()).strip()

    @staticmethod
    def _extract_authors(author_list):
        if author_list is None:
            return ""
        names = []
        for author in author_list.findall("Author"):
            last = IncrementalSync._text(author.find("LastName"))
            fore = IncrementalSync._text(author.find("ForeName"))
            if last and fore:
                names.append(f"{last}, {fore}")
            elif last:
                names.append(last)
        return "; ".join(names)

    @staticmethod
    def _extract_abstract(abstract_node):
        if abstract_node is None:
            return ""
        parts = []
        for text_node in abstract_node.findall("AbstractText"):
            label = text_node.attrib.get("Label")
            text = IncrementalSync._text(text_node)
            if label:
                parts.append(f"{label}: {text}")
            else:
                parts.append(text)
        return " ".join(parts).strip()

    @staticmethod
    def _format_pub_date(pub_date_node):
        if pub_date_node is None:
            return ""
        year = IncrementalSync._text(pub_date_node.find("Year"))
        month = IncrementalSync._text(pub_date_node.find("Month"))
        day = IncrementalSync._text(pub_date_node.find("Day"))
        parts = [part for part in (year, month, day) if part]
        return "-".join(parts)
