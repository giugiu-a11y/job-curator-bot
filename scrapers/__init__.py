"""
Job Curator Bot - Scrapers
"""
from .base import BaseScraper
from .remoteok import RemoteOKScraper
from .weworkremotely import WeWorkRemotelyScraper
from .himalayas import HimalayasScraper

# Lista de todos os scrapers disponíveis
ALL_SCRAPERS = [
    RemoteOKScraper,
    WeWorkRemotelyScraper,
    HimalayasScraper,
]

def get_all_scrapers():
    """Retorna instâncias de todos os scrapers"""
    return [scraper() for scraper in ALL_SCRAPERS]
