"""
Job Curator Bot - Base Scraper
Classe base para todos os scrapers
"""
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

import requests

from config import USER_AGENT, REQUEST_TIMEOUT, REQUEST_DELAY

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Classe base para scrapers de vagas"""
    
    name: str = "base"
    base_url: str = ""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'application/json, text/html, */*',
        })
    
    def generate_job_id(self, unique_string: str) -> str:
        """Gera um ID único para a vaga"""
        content = f"{self.name}:{unique_string}"
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def make_request(self, url: str, method: str = 'GET', **kwargs) -> Optional[requests.Response]:
        """Faz uma requisição HTTP com tratamento de erros"""
        try:
            kwargs.setdefault('timeout', REQUEST_TIMEOUT)
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.name}] Erro na requisição {url}: {e}")
            return None
    
    def rate_limit(self):
        """Aplica rate limiting entre requisições"""
        time.sleep(REQUEST_DELAY)
    
    @abstractmethod
    def fetch_jobs(self, limit: int = 50) -> List[Dict]:
        """
        Busca vagas da fonte.
        
        Args:
            limit: número máximo de vagas para buscar
        
        Returns:
            Lista de dicts com dados das vagas no formato padrão:
            {
                'id': str,
                'title': str,
                'company': str,
                'description': str,
                'source_url': str,
                'location': str,
                'salary_min': int ou None,
                'salary_max': int ou None,
                'salary_currency': str,
                'tags': list,
                'raw_data': dict (dados originais),
            }
        """
        pass
    
    def normalize_job(self, raw_job: dict) -> Dict:
        """
        Normaliza dados de uma vaga para o formato padrão.
        Sobrescrever nas subclasses.
        """
        return raw_job
    
    def run(self, limit: int = 50) -> List[Dict]:
        """Executa o scraper e retorna vagas normalizadas"""
        logger.info(f"[{self.name}] Iniciando scraping (limite: {limit})")
        
        try:
            jobs = self.fetch_jobs(limit)
            logger.info(f"[{self.name}] {len(jobs)} vagas encontradas")
            return jobs
        except Exception as e:
            logger.error(f"[{self.name}] Erro no scraping: {e}")
            return []
