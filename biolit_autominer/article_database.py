import sqlite3
from datetime import datetime
from pathlib import Path

class ArticleDatabase:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                pmid TEXT PRIMARY KEY,
                pmcid TEXT,
                title TEXT,
                authors TEXT,
                pub_date TEXT,
                journal TEXT,
                status TEXT,
                has_full_text INTEGER,
                source TEXT,
                full_text_url TEXT,
                gemini_processed INTEGER,
                gemini_result TEXT,
                error_message TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_log (
                sync_date TIMESTAMP PRIMARY KEY,
                total_articles INTEGER,
                new_articles INTEGER,
                processed INTEGER,
                errors INTEGER,
                notes TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_article(self, pmid, data):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO articles
            (pmid, pmcid, title, authors, pub_date, journal, status, 
             has_full_text, source, full_text_url, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            pmid,
            data.get('pmcid'),
            data.get('title'),
            data.get('authors'),
            data.get('pub_date'),
            data.get('journal'),
            data.get('status', 'new'),
            data.get('has_full_text', 0),
            data.get('source'),
            data.get('full_text_url'),
            datetime.now(),
            datetime.now()
        ))
        
        conn.commit()
        conn.close()
    
    def get_existing_pmids(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT pmid FROM articles')
        pmids = set([row[0] for row in cursor.fetchall()])
        conn.close()
        return pmids
    
    def export_to_excel(self, output_path):
        try:
            import pandas as pd
            conn = sqlite3.connect(self.db_path)
            df = pd.read_sql_query("SELECT * FROM articles", conn)
            df.to_excel(output_path, sheet_name='Articles', index=False)
            conn.close()
            print(f"✓ Exported to {output_path}")
        except Exception as e:
            print(f"❌ Export failed: {e}")
    
    def print_stats(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM articles')
        total = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM articles WHERE status = "processed"')
        processed = cursor.fetchone()[0]
        conn.close()
        print(f"Total articles: {total}, Processed: {processed}")
