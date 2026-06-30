from .article_database import ArticleDatabase
from .pubmed_scraper import PubMedScraper
from .incremental_sync import IncrementalSync

class EnhancedAutoPipeline:
    def __init__(self, email, api_key=None, gemini_project_id=None, output_dir=None):
        self.email = email
        self.api_key = api_key
        self.gemini_project_id = gemini_project_id
        self.output_dir = output_dir or "auto_pipeline_output"
        
        self.db = ArticleDatabase(f"{self.output_dir}/articles.db")
        self.scraper = PubMedScraper()
        self.sync = IncrementalSync(email, api_key)
    
    def full_workflow(self, search_query):
        print("Starting workflow...")
        
        # Step 1: Get existing PMIDs
        existing_pmids = self.db.get_existing_pmids()
        print(f"Existing articles: {len(existing_pmids)}")
        
        # Step 2: Search for new articles
        new_pmids = self.sync.get_new_articles(search_query, existing_pmids)
        print(f"New articles found: {len(new_pmids)}")
        
        # Step 3: Get links for new articles
        if new_pmids:
            results = self.scraper.batch_get_links(new_pmids[:10])  # Limit to 10
            
            for result in results:
                self.db.add_article(result['pmid'], {
                    'has_full_text': result['has_full_text_link'],
                    'status': 'new'
                })
        
        # Step 4: Export to Excel
        self.db.export_to_excel(f"{self.output_dir}/articles_database.xlsx")
        
        return {
            'status': 'completed',
            'new_articles': len(new_pmids),
            'processed': min(len(new_pmids), 10)
        }
