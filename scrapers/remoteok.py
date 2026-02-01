"""
Job Curator Bot - RemoteOK Scraper
"""
import logging
from typing import List, Dict

from .base import BaseScraper

logger = logging.getLogger(__name__)


class RemoteOKScraper(BaseScraper):
    """Scraper para RemoteOK.com"""
    
    name = "remoteok"
    base_url = "https://remoteok.com"
    api_url = "https://remoteok.com/api"
    
    def fetch_jobs(self, limit: int = 50) -> List[Dict]:
        """Busca vagas via API JSON do RemoteOK"""
        
        response = self.make_request(self.api_url)
        if not response:
            return []
        
        try:
            data = response.json()
        except:
            logger.error(f"[{self.name}] Erro ao parsear JSON")
            return []
        
        jobs = []
        
        # Primeiro item é metadata, pula
        for item in data[1:limit+1]:
            try:
                job = self.normalize_job(item)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.warning(f"[{self.name}] Erro ao normalizar vaga: {e}")
                continue
        
        return jobs
    
    def normalize_job(self, raw: dict) -> Dict:
        """Normaliza vaga do RemoteOK"""
        
        job_id = self.generate_job_id(str(raw.get('id', raw.get('slug', ''))))
        
        # Extrai salário se disponível
        salary_min = None
        salary_max = None
        if raw.get('salary_min'):
            try:
                salary_min = int(raw['salary_min'])
            except:
                pass
        if raw.get('salary_max'):
            try:
                salary_max = int(raw['salary_max'])
            except:
                pass
        
        # Monta URL da vaga
        slug = raw.get('slug', raw.get('id', ''))
        source_url = f"{self.base_url}/remote-jobs/{slug}" if slug else None
        
        # Tags
        tags = raw.get('tags', [])
        if isinstance(tags, str):
            tags = [tags]
        
        return {
            'id': job_id,
            'title': raw.get('position', 'N/A'),
            'company': raw.get('company', 'N/A'),
            'description': raw.get('description', ''),
            'source_url': source_url,
            'location': raw.get('location', 'Remote'),
            'salary_min': salary_min,
            'salary_max': salary_max,
            'salary_currency': 'USD',
            'tags': tags,
            'raw_data': raw,
        }
