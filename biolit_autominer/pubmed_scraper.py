import requests
from bs4 import BeautifulSoup

class PubMedScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
        }
    
    def get_full_text_links(self, pmid):
        try:
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code != 200:
                return {"pmid": pmid, "has_full_text_link": False, "links": []}
            
            soup = BeautifulSoup(response.content, 'html.parser')
            links = []
            
            # Find full text links
            for link in soup.find_all('a', class_='full-text-links-list__link'):
                links.append({
                    "text": link.get_text(),
                    "url": link.get('href'),
                    "publisher": self._identify_publisher(link.get('href', ''))
                })
            
            return {
                "pmid": pmid,
                "has_full_text_link": len(links) > 0,
                "links": links
            }
        except Exception as e:
            return {"pmid": pmid, "has_full_text_link": False, "error": str(e)}
    
    def batch_get_links(self, pmids):
        results = []
        for pmid in pmids:
            results.append(self.get_full_text_links(pmid))
        return results
    
    def _identify_publisher(self, url):
        publishers = ['elsevier', 'springer', 'wiley', 'nature', 'science', 'plos']
        url_lower = url.lower()
        for pub in publishers:
            if pub in url_lower:
                return pub
        return 'unknown'

class FullTextDownloader:
    pass
