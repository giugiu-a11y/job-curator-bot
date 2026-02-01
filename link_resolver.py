"""
Job Curator Bot - Link Resolver
Resolve links de agregadores para links diretos das empresas
(Greenhouse, Lever, Workday, etc)
"""
import re
import time
import logging
from urllib.parse import urlparse, urljoin
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup

from config import (
    VALID_JOB_DOMAINS, 
    AGGREGATOR_DOMAINS,
    REQUEST_TIMEOUT,
    REQUEST_DELAY,
    USER_AGENT
)

logger = logging.getLogger(__name__)

# Headers para requests
HEADERS = {
    'User-Agent': USER_AGENT,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


def is_valid_direct_url(url: str) -> bool:
    """Verifica se a URL é um link direto válido (não agregador)"""
    if not url:
        return False
    
    parsed = urlparse(url.lower())
    domain = parsed.netloc
    
    # Verifica se é um domínio de job board direto
    for valid_domain in VALID_JOB_DOMAINS:
        if valid_domain in domain:
            return True
    
    # Verifica se é um careers page da empresa (não agregador)
    for agg_domain in AGGREGATOR_DOMAINS:
        if agg_domain in domain:
            return False
    
    # Se tem /careers/ ou /jobs/ no path, provavelmente é direto
    path = parsed.path.lower()
    if any(x in path for x in ['/careers/', '/jobs/', '/job/', '/position/', '/vacancy/']):
        # Mas não se for um agregador
        if not any(agg in domain for agg in AGGREGATOR_DOMAINS):
            return True
    
    return False


def is_aggregator_url(url: str) -> bool:
    """Verifica se a URL é de um agregador"""
    if not url:
        return False
    
    parsed = urlparse(url.lower())
    domain = parsed.netloc
    
    for agg_domain in AGGREGATOR_DOMAINS:
        if agg_domain in domain:
            return True
    
    return False


def extract_apply_links(html: str, base_url: str) -> list:
    """Extrai possíveis links de aplicação de uma página HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    links = []
    
    # Padrões de botões/links de "Apply"
    apply_patterns = [
        r'apply',
        r'candidatar',
        r'inscrever',
        r'submit.*application',
        r'job.*application',
    ]
    
    # Busca por links
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        text = a.get_text().lower().strip()
        classes = ' '.join(a.get('class', [])).lower()
        
        # Pula links vazios ou âncoras
        if not href or href.startswith('#') or href.startswith('javascript:'):
            continue
        
        # Converte para URL absoluta
        full_url = urljoin(base_url, href)
        
        # Verifica se é um link de apply
        is_apply_link = any(re.search(p, text) or re.search(p, classes) for p in apply_patterns)
        
        # Verifica se aponta para um job board direto
        if is_valid_direct_url(full_url):
            links.append((full_url, 'direct_domain', 10))
        elif is_apply_link and not is_aggregator_url(full_url):
            links.append((full_url, 'apply_button', 8))
    
    # Busca por iframes (alguns usam iframe do Greenhouse/Lever)
    for iframe in soup.find_all('iframe', src=True):
        src = iframe.get('src', '')
        full_url = urljoin(base_url, src)
        if is_valid_direct_url(full_url):
            links.append((full_url, 'iframe', 9))
    
    # Busca links no texto que parecem ser de job boards
    for pattern, domain in [
        (r'https?://boards\.greenhouse\.io/[^\s"\'<>]+', 'greenhouse'),
        (r'https?://jobs\.lever\.co/[^\s"\'<>]+', 'lever'),
        (r'https?://[a-z0-9-]+\.workday\.com/[^\s"\'<>]+', 'workday'),
        (r'https?://jobs\.ashbyhq\.com/[^\s"\'<>]+', 'ashby'),
        (r'https?://[a-z0-9-]+\.bamboohr\.com/[^\s"\'<>]+', 'bamboo'),
    ]:
        matches = re.findall(pattern, html, re.IGNORECASE)
        for match in matches:
            links.append((match, f'regex_{domain}', 9))
    
    # Remove duplicatas mantendo maior score
    seen = {}
    for url, source, score in links:
        if url not in seen or seen[url][1] < score:
            seen[url] = (source, score)
    
    # Retorna ordenado por score
    result = [(url, source, score) for url, (source, score) in seen.items()]
    result.sort(key=lambda x: x[2], reverse=True)
    
    return result


def fetch_page(url: str) -> Optional[str]:
    """Faz request para uma URL e retorna o HTML"""
    try:
        response = requests.get(
            url, 
            headers=HEADERS, 
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.warning(f"Erro ao buscar {url}: {e}")
        return None


def follow_redirects(url: str) -> Optional[str]:
    """Segue redirects e retorna a URL final"""
    try:
        response = requests.head(
            url, 
            headers=HEADERS, 
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )
        return response.url
    except:
        try:
            response = requests.get(
                url, 
                headers=HEADERS, 
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
                stream=True  # Não baixa o conteúdo todo
            )
            return response.url
        except Exception as e:
            logger.warning(f"Erro ao seguir redirects de {url}: {e}")
            return None


def verify_url_is_active(url: str) -> bool:
    """Verifica se uma URL ainda está ativa (não 404)"""
    try:
        response = requests.head(
            url, 
            headers=HEADERS, 
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )
        return response.status_code < 400
    except:
        try:
            response = requests.get(
                url, 
                headers=HEADERS, 
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
                stream=True
            )
            return response.status_code < 400
        except:
            return False


def resolve_direct_url(source_url: str) -> Tuple[Optional[str], str]:
    """
    Resolve uma URL de agregador para o link direto da empresa.
    
    Returns:
        Tuple[Optional[str], str]: (url_direta ou None, motivo)
    """
    logger.info(f"Resolvendo link: {source_url}")
    
    # Se já é um link direto válido, retorna ele mesmo
    if is_valid_direct_url(source_url):
        if verify_url_is_active(source_url):
            logger.info(f"  ✅ Já é link direto válido")
            return source_url, "already_direct"
        else:
            logger.warning(f"  ❌ Link direto mas inativo (404)")
            return None, "direct_but_inactive"
    
    # Primeiro tenta seguir redirects
    final_url = follow_redirects(source_url)
    if final_url and is_valid_direct_url(final_url):
        logger.info(f"  ✅ Redirect para link direto: {final_url}")
        return final_url, "redirect"
    
    # Se não, busca a página e procura links
    time.sleep(REQUEST_DELAY)  # Rate limiting
    
    html = fetch_page(source_url)
    if not html:
        return None, "fetch_failed"
    
    # Extrai possíveis links de apply
    links = extract_apply_links(html, source_url)
    
    if not links:
        logger.warning(f"  ❌ Nenhum link de aplicação encontrado")
        return None, "no_apply_links"
    
    # Tenta cada link encontrado
    for url, source, score in links:
        logger.debug(f"  Testando: {url} (source={source}, score={score})")
        
        # Segue redirects deste link
        final = follow_redirects(url)
        if final and is_valid_direct_url(final):
            if verify_url_is_active(final):
                logger.info(f"  ✅ Link direto encontrado: {final}")
                return final, f"extracted_{source}"
        
        time.sleep(0.5)  # Pequeno delay entre tentativas
    
    # Se chegou aqui, não encontrou link direto válido
    logger.warning(f"  ❌ Não foi possível resolver para link direto")
    return None, "no_valid_direct_found"


def batch_resolve_urls(jobs: list, max_workers: int = 1) -> dict:
    """
    Resolve URLs em batch (sequencial para respeitar rate limits)
    
    Returns:
        dict: {job_id: (direct_url, status)}
    """
    results = {}
    
    for i, job in enumerate(jobs):
        job_id = job.get('id')
        source_url = job.get('source_url')
        
        logger.info(f"[{i+1}/{len(jobs)}] Processando: {job.get('title', 'N/A')[:50]}")
        
        if not source_url:
            results[job_id] = (None, "no_source_url")
            continue
        
        direct_url, status = resolve_direct_url(source_url)
        results[job_id] = (direct_url, status)
        
        time.sleep(REQUEST_DELAY)  # Rate limiting entre jobs
    
    return results
