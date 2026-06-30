from Bio import Entrez

class IncrementalSync:
    def __init__(self, email, api_key=None):
        self.email = email
        self.api_key = api_key
        Entrez.email = email
        if api_key:
            Entrez.api_key = api_key
    
    def search_pubmed(self, query, max_results=100):
        try:
            handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results)
            result = Entrez.read(handle)
            handle.close()
            return result.get("IdList", [])
        except Exception as e:
            print(f"❌ Search failed: {e}")
            return []
    
    def get_new_articles(self, query, existing_pmids, max_results=100):
        all_pmids = self.search_pubmed(query, max_results)
        new_pmids = [p for p in all_pmids if p not in existing_pmids]
        return new_pmids
    
    def map_pmid_to_pmcid(self, pmid):
        try:
            handle = Entrez.elink(dbfrom="pubmed", db="pmc", id=pmid)
            result = Entrez.read(handle)
            handle.close()
            
            if result[0]['LinkSetDb']:
                return result[0]['LinkSetDb'][0]['Link'][0]['Id']
            return None
        except Exception as e:
            print(f"❌ Mapping failed: {e}")
            return None

