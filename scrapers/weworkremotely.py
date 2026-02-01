"""
Job Curator Bot - We Work Remotely Scraper
"""
import logging
import re
from typing import List, Dict

import feedparser
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)


class WeWorkRemotelyScraper(BaseScraper):
    """Scraper para WeWorkRemotely.com via RSS"""
    
    name = "weworkremotely"
    base_url = "https://weworkremotely.com"
    
    # RSS feeds por categoria
    rss_feeds = [
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-design-jobs.rss",
        "https://weworkremotely.com/categories/remote-sales-and-marketing-jobs.rss",
        "https://weworkremotely.com/categories/remote-customer-support-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
        "https://weworkremotely.com/categories/remote-finance-and-legal-jobs.rss",
        "https://weworkremotely.com/categories/remote-product-jobs.rss",
        "https://weworkremotely.com/categories/remote-data-jobs.rss",
        "https://weworkremotely.com/categories/remote-executive-jobs.rss",
        "https://weworkremotely.com/categories/remote-all-other-jobs.rss",
    ]
    
    def fetch_jobs(self, limit: int = 50) -> List[Dict]:
        """Busca vagas via RSS feeds do WWR"""
        
        all_jobs = []
        per_feed_limit = max(5, limit // len(self.rss_feeds))
        
        for feed_url in self.rss_feeds:
            try:
                feed = feedparser.parse(feed_url)
                
                for entry in feed.entries[:per_feed_limit]:
                    try:
                        job = self.normalize_job(entry, feed_url)
                        if job:
                            all_jobs.append(job)
                    except Exception as e:
                        logger.warning(f"[{self.name}] Erro ao normalizar: {e}")
                        continue
                
                self.rate_limit()
                
            except Exception as e:
                logger.error(f"[{self.name}] Erro ao processar feed {feed_url}: {e}")
                continue
            
            if len(all_jobs) >= limit:
                break
        
        return all_jobs[:limit]
    
    def normalize_job(self, entry: dict, feed_url: str) -> Dict:
        """Normaliza entrada RSS do WWR"""
        
        job_id = self.generate_job_id(entry.get('link', entry.get('id', '')))
        
        # Extrai empresa do título (formato: "Empresa: Título da Vaga")
        title = entry.get('title', '')
        company = 'N/A'
        if ':' in title:
            parts = title.split(':', 1)
            company = parts[0].strip()
            title = parts[1].strip()
        
        # Extrai categoria do feed URL
        category = 'Other'
        if 'programming' in feed_url:
            category = 'Technology'
        elif 'design' in feed_url:
            category = 'Design'
        elif 'marketing' in feed_url or 'sales' in feed_url:
            category = 'Marketing'
        elif 'support' in feed_url:
            category = 'Operations'
        elif 'finance' in feed_url or 'legal' in feed_url:
            category = 'Operations'
        elif 'data' in feed_url:
            category = 'AI/ML'
        elif 'executive' in feed_url:
            category = 'Operations'
        
        # Descrição (remove HTML)
        description = entry.get('description', entry.get('summary', ''))
        if description:
            soup = BeautifulSoup(description, 'html.parser')
            description = soup.get_text(separator=' ', strip=True)
        
        return {
            'id': job_id,
            'title': title,
            'company': company,
            'description': description,
            'source_url': entry.get('link'),
            'location': 'Remote',
            'salary_min': None,
            'salary_max': None,
            'salary_currency': 'USD',
            'tags': [category],
            'raw_data': dict(entry),
        }
