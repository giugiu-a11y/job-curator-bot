"""
Job Curator Bot - Himalayas.app Scraper
Himalayas é ótimo para vagas remote-first que aceitam global
"""
import logging
from typing import List, Dict

from .base import BaseScraper

logger = logging.getLogger(__name__)


class HimalayasScraper(BaseScraper):
    """Scraper para Himalayas.app via API pública"""
    
    name = "himalayas"
    base_url = "https://himalayas.app"
    api_url = "https://himalayas.app/jobs/api"
    
    def fetch_jobs(self, limit: int = 50) -> List[Dict]:
        """Busca vagas via API do Himalayas"""
        
        # A API do Himalayas aceita parâmetros de filtro
        params = {
            'limit': min(limit, 100),
            'offset': 0,
        }
        
        response = self.make_request(self.api_url, params=params)
        if not response:
            return []
        
        try:
            data = response.json()
        except:
            logger.error(f"[{self.name}] Erro ao parsear JSON")
            return []
        
        jobs = []
        job_list = data.get('jobs', data) if isinstance(data, dict) else data
        
        if not isinstance(job_list, list):
            logger.error(f"[{self.name}] Formato inesperado de resposta")
            return []
        
        for item in job_list[:limit]:
            try:
                job = self.normalize_job(item)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.warning(f"[{self.name}] Erro ao normalizar vaga: {e}")
                continue
        
        return jobs
    
    def normalize_job(self, raw: dict) -> Dict:
        """Normaliza vaga do Himalayas"""
        
        job_id = self.generate_job_id(str(raw.get('id', raw.get('slug', ''))))
        
        # Extrai salário
        salary_min = None
        salary_max = None
        salary_data = raw.get('salary') or {}
        
        if isinstance(salary_data, dict):
            salary_min = salary_data.get('min')
            salary_max = salary_data.get('max')
        elif raw.get('minSalary'):
            salary_min = raw.get('minSalary')
            salary_max = raw.get('maxSalary')
        
        # Converte para int se necessário
        if salary_min:
            try:
                salary_min = int(salary_min)
            except:
                salary_min = None
        if salary_max:
            try:
                salary_max = int(salary_max)
            except:
                salary_max = None
        
        # URL da vaga
        slug = raw.get('slug', raw.get('id', ''))
        company_slug = raw.get('companySlug', raw.get('company', {}).get('slug', ''))
        
        if slug and company_slug:
            source_url = f"{self.base_url}/companies/{company_slug}/jobs/{slug}"
        elif slug:
            source_url = f"{self.base_url}/jobs/{slug}"
        else:
            source_url = None
        
        # Empresa
        company = raw.get('companyName') or raw.get('company', {}).get('name', 'N/A')
        
        # Localização
        location = raw.get('locationRestrictions') or raw.get('location') or 'Worldwide'
        if isinstance(location, list):
            location = ', '.join(location) if location else 'Worldwide'
        
        # Categoria
        category = raw.get('category') or raw.get('department') or 'Other'
        
        # Tags
        tags = raw.get('tags', [])
        if not isinstance(tags, list):
            tags = [tags] if tags else []
        tags.append(category)
        
        return {
            'id': job_id,
            'title': raw.get('title', 'N/A'),
            'company': company,
            'description': raw.get('description', raw.get('excerpt', '')),
            'source_url': source_url,
            'location': location,
            'salary_min': salary_min,
            'salary_max': salary_max,
            'salary_currency': raw.get('salaryCurrency', 'USD'),
            'tags': tags,
            'raw_data': raw,
        }
