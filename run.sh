#!/bin/bash
# Job Curator Bot - Script simplificado
# Descobre → Filtra → Posta

export PYTHONPATH=/home/ubuntu/projects/job-curator-bot:$PYTHONPATH
cd /home/ubuntu/projects/job-curator-bot

# Load global env (if present)
if [ -r /etc/llm.env ]; then
  set -a
  . /etc/llm.env || true
  set +a
fi
# Load env (override global)
export $(grep -v '^#' .env | xargs)

# 1. Descobre vagas
echo "🔍 Descobrindo vagas..."
python3 << 'PYSCRIPT'
import feedparser
import json
import re
import requests
import time
import os
from bs4 import BeautifulSoup
from datetime import datetime

jobs = []

ALLOWED_REGEXES = [
    re.compile(r'\b(united states|u\.s\.|usa|us)\b', re.I),
    re.compile(r'\bcanada\b', re.I),
    re.compile(r'\b(europe|eu|eea|european union)\b', re.I),
    re.compile(r'\b(uk|united kingdom|england|scotland|wales|ireland)\b', re.I),
    re.compile(r'\b(germany|france|spain|portugal|italy|netherlands|belgium|sweden|norway|denmark|finland)\b', re.I),
    re.compile(r'\b(poland|austria|switzerland|czech|slovakia|hungary|romania|bulgaria|greece)\b', re.I),
    re.compile(r'\b(iceland|luxembourg|estonia|latvia|lithuania|croatia|slovenia)\b', re.I),
]

BLOCKED_TERMS = [
    'latin america', 'latam', 'south america',
    'brazil', 'brasil', 'mexico', 'argentina', 'colombia', 'chile', 'peru',
    'uruguay', 'paraguay', 'bolivia', 'ecuador', 'venezuela',
    'guatemala', 'costa rica', 'panama', 'dominican', 'puerto rico',
]

PORTUGUESE_HINTS = [
    'portuguese', 'português', 'portugues', 'pt-br', 'pt br', 'pt/br',
    'brazilian portuguese',
]
BRAVE_TOKEN = (
    (os.environ.get('BRAVE_API_KEY') or '')
    or (os.environ.get('BRAVE_SEARCH_API_KEY') or '')
    or (os.environ.get('BRAVE_SUBSCRIPTION_TOKEN') or '')
)
BRAVE_ENDPOINT = 'https://api.search.brave.com/res/v1/web/search'
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def is_allowed_location(location_text: str, description_text: str = "") -> bool:
    text = f"{location_text} {description_text}".lower()
    if any(term in text for term in BLOCKED_TERMS):
        return False
    for rx in ALLOWED_REGEXES:
        if rx.search(text):
            return True
    return False

def has_portuguese_hint(text: str) -> bool:
    text = (text or '').lower()
    return any(h in text for h in PORTUGUESE_HINTS)

def clean_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '').strip()

def strip_html(text: str) -> str:
    raw = text or ''
    if '<' not in raw and '>' not in raw:
        return clean_whitespace(raw)
    try:
        soup = BeautifulSoup(raw, 'html.parser')
        return clean_whitespace(soup.get_text(' ', strip=True))
    except Exception:
        return clean_whitespace(raw)

def infer_salary(text: str) -> str:
    """Heurística simples: tenta achar salário e padroniza em USD/mês."""
    t = (text or '').lower()
    # padrões como "$120,000" ou "usd 120k"
    money = re.findall(r'(?:usd|us\\$|\\$)\\s?([0-9]{2,3}(?:[,\\.][0-9]{3})+|[0-9]{2,3}k)', t)
    if not money:
        return ''
    # usa o primeiro valor encontrado
    raw = money[0].replace(',', '').replace('.', '').lower()
    try:
        if raw.endswith('k'):
            value = int(raw[:-1]) * 1000
        else:
            value = int(raw)
    except Exception:
        return ''
    # se texto indicar ano, converte para mês
    per_year = any(x in t for x in ['per year', 'year', 'annual', '/year', 'yr', 'a year'])
    per_month = any(x in t for x in ['per month', 'month', '/mo', '/month', 'monthly'])
    if per_month:
        monthly = value
    else:
        monthly = int(value / 12) if per_year or value > 20000 else value
    if monthly < 500:
        return ''
    return f"USD ${monthly:,}/mês"

def normalize_location(loc) -> str:
    if not loc:
        return "Remoto"
    if isinstance(loc, str):
        return clean_whitespace(loc)
    if isinstance(loc, list):
        parts = []
        for item in loc:
            if isinstance(item, dict):
                term = item.get('term') or item.get('label') or ''
                if term:
                    parts.append(term)
            elif isinstance(item, str):
                parts.append(item)
        return clean_whitespace(', '.join(parts)) if parts else "Remoto"
    if isinstance(loc, dict):
        term = loc.get('term') or loc.get('label') or ''
        return clean_whitespace(term) if term else "Remoto"
    return "Remoto"

def infer_location_from_text(text: str) -> str:
    t = (text or '').lower()
    if any(x in t for x in ['united states', 'u.s.', 'usa', 'us only', 'us']):
        return 'United States'
    if 'canada' in t:
        return 'Canada'
    if any(x in t for x in ['united kingdom', 'uk', 'england', 'scotland', 'wales']):
        return 'United Kingdom'
    if 'ireland' in t:
        return 'Ireland'
    if 'germany' in t:
        return 'Germany'
    if 'france' in t:
        return 'France'
    if 'netherlands' in t:
        return 'Netherlands'
    if 'spain' in t:
        return 'Spain'
    if 'portugal' in t:
        return 'Portugal'
    if 'sweden' in t:
        return 'Sweden'
    if 'denmark' in t:
        return 'Denmark'
    if 'norway' in t:
        return 'Norway'
    if 'finland' in t:
        return 'Finland'
    if 'italy' in t:
        return 'Italy'
    if 'poland' in t:
        return 'Poland'
    if 'switzerland' in t:
        return 'Switzerland'
    if 'austria' in t:
        return 'Austria'
    if 'czech' in t:
        return 'Czech Republic'
    return ''

def brave_search(query: str, count: int = 10, offset: int = 0) -> list:
    if not BRAVE_TOKEN:
        return []
    params = {
        'q': query,
        'count': count,
        'offset': offset,
        'search_lang': 'en',
        'safesearch': 'moderate',
    }
    headers = {'X-Subscription-Token': BRAVE_TOKEN}
    try:
        r = requests.get(BRAVE_ENDPOINT, params=params, headers=headers, timeout=20)
        if not r.ok:
            return []
        data = r.json()
        results = data.get('web', {}).get('results', []) if isinstance(data, dict) else []
        return results
    except Exception:
        return []

def extract_page_text(url: str) -> str:
    try:
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=20)
        if not r.ok:
            return ''
        soup = BeautifulSoup(r.text, 'html.parser')
        for tag in soup(['script', 'style', 'noscript']):
            tag.decompose()
        text = clean_whitespace(soup.get_text(' ', strip=True))
        return text[:2000]
    except Exception:
        return ''

def extract_title_company(url: str, text: str) -> tuple:
    title = ''
    company = ''
    # Try to parse from title in HTML
    try:
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=20)
        if r.ok:
            soup = BeautifulSoup(r.text, 'html.parser')
            og = soup.find('meta', attrs={'property': 'og:title'})
            if og and og.get('content'):
                title = og.get('content')
            if not title and soup.title and soup.title.string:
                title = soup.title.string
    except Exception:
        pass
    if not title:
        title = text[:80] if text else 'N/A'
    # Heurística simples: "Role - Company" ou "Role | Company"
    if ' - ' in title:
        parts = title.split(' - ', 1)
        title = parts[0].strip()
        company = parts[1].strip()
    elif ' | ' in title:
        parts = title.split(' | ', 1)
        title = parts[0].strip()
        company = parts[1].strip()
    return title.strip(), (company.strip() or 'Unknown')
def extract_jobbank_description(job_url: str) -> str:
    try:
        r = requests.get(job_url, timeout=20)
        if not r.ok:
            return ''
        soup = BeautifulSoup(r.text, 'html.parser')
        main = soup.find('main')
        if not main:
            main = soup
        text = clean_whitespace(main.get_text(' ', strip=True))
        # Heurística: pega trecho após "Tasks" se existir
        idx = text.lower().find('tasks:')
        if idx != -1:
            text = text[idx:idx+800]
        return text[:800]
    except Exception:
        return ''

# WWR
print("  → We Work Remotely...")
try:
    feeds = [
        'https://weworkremotely.com/categories/remote-programming-jobs.rss',
        'https://weworkremotely.com/categories/remote-design-jobs.rss',
        'https://weworkremotely.com/categories/remote-sales-and-marketing-jobs.rss',
        'https://weworkremotely.com/categories/remote-customer-support-jobs.rss',
        'https://weworkremotely.com/categories/remote-product-jobs.rss',
        'https://weworkremotely.com/categories/remote-data-jobs.rss',
    ]
    for feed_url in feeds:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:10]:
            summary = strip_html(entry.get('summary', ''))[:800]
            location = entry.get('location', '') or entry.get('tags', '')
            if not is_allowed_location(location, summary):
                continue
            jobs.append({
                'id': entry.get('id', entry.get('link', '')),
                'title': entry.get('title', 'N/A'),
                'company': entry.get('author', 'Unknown'),
                'link': entry.get('link', ''),
                'description': summary,
                'location': location,
                'pt_hint': has_portuguese_hint(summary),
                'source': 'weworkremotely'
            })
except Exception:
    pass

# Himalayas
print("  → Himalayas...")
try:
    feed = feedparser.parse('https://himalayas.app/rss')
    for entry in feed.entries[:20]:
        summary = strip_html(entry.get('summary', ''))[:800]
        location = entry.get('location', '') or entry.get('tags', '')
        if not is_allowed_location(location, summary):
            continue
        jobs.append({
            'id': entry.get('id', entry.get('link', '')),
            'title': entry.get('title', 'N/A'),
            'company': entry.get('author', 'Unknown'),
            'link': entry.get('link', ''),
            'description': summary,
            'location': location,
            'pt_hint': has_portuguese_hint(summary),
            'source': 'himalayas'
        })
except Exception:
    pass

# Remotive (API)
print("  → Remotive...")
try:
    r = requests.get('https://remotive.com/api/remote-jobs', timeout=20)
    data = r.json() if r.ok else {}
    for item in (data.get('jobs') or [])[:50]:
        location = item.get('candidate_required_location', '') or item.get('location', '')
        description = strip_html(item.get('description') or '')[:800]
        if not is_allowed_location(location, description):
            continue
        jobs.append({
            'id': item.get('id', item.get('url', '')),
            'title': item.get('title', 'N/A'),
            'company': item.get('company_name', 'Unknown'),
            'link': item.get('url', ''),
            'description': description,
            'location': location,
            'pt_hint': has_portuguese_hint(description),
            'source': 'remotive'
        })
except Exception:
    pass

# RemoteOK (API)
print("  → RemoteOK...")
try:
    r = requests.get('https://remoteok.com/api', timeout=20)
    data = r.json() if r.ok else []
    for item in data[1:51]:
        location = item.get('location', '') or ''
        description = strip_html(item.get('description') or '')[:800]
        if not is_allowed_location(location, description):
            continue
        jobs.append({
            'id': item.get('id', item.get('url', '')),
            'title': item.get('position', 'N/A'),
            'company': item.get('company', 'Unknown'),
            'link': item.get('url', ''),
            'description': description,
            'location': location,
            'pt_hint': has_portuguese_hint(description),
            'source': 'remoteok'
        })
except Exception:
    pass

# Brave Search (Greenhouse/Lever visa sponsorship)
print("  → Brave Search (visa sponsorship)...")
try:
    if BRAVE_TOKEN:
        queries = [
            'site:greenhouse.io "visa sponsorship" "United States"',
            'site:lever.co "visa sponsorship" "United States"',
            'site:greenhouse.io "visa sponsorship" Canada',
            'site:lever.co "visa sponsorship" Canada',
            'site:greenhouse.io "visa sponsorship" "United Kingdom"',
            'site:lever.co "visa sponsorship" "United Kingdom"',
            'site:greenhouse.io "visa sponsorship" Germany',
            'site:lever.co "visa sponsorship" Germany',
        ]
        seen = set()
        for q in queries:
            results = brave_search(q, count=8)
            time.sleep(2)
            for item in results:
                url = item.get('url') or ''
                if not url or url in seen:
                    continue
                if 'greenhouse.io' not in url and 'lever.co' not in url:
                    continue
                if '/jobs/' not in url:
                    continue
                seen.add(url)
                text = extract_page_text(url)
                location = infer_location_from_text(text)
                if not is_allowed_location(location, text):
                    continue
                title, company = extract_title_company(url, text)
                jobs.append({
                    'id': f"brave-{hash(url)}",
                    'title': title or 'N/A',
                    'company': company or 'Unknown',
                    'link': url,
                    'description': text[:800],
                    'location': location or 'Remote',
                    'pt_hint': has_portuguese_hint(text),
                    'source': 'brave-search'
                })
                time.sleep(3)
                if len(jobs) >= 200:
                    break
            if len(jobs) >= 200:
                break
    else:
        print("    (Brave API key não configurada; pulando)")
except Exception:
    pass

# Job Bank (Canadá) - Foreign Candidates (fglo=1)
print("  → Job Bank (Canada)...")
try:
    r = requests.get('https://www.jobbank.gc.ca/jobsearch/jobsearch?sort=M&fglo=1', timeout=20)
    html = r.text if r.ok else ''
    # encontra blocos de artigo
    for match in re.finditer(r'<article id=\"article-(\\d+)\"[\\s\\S]*?</article>', html):
        block = match.group(0)
        # link
        link_match = re.search(r'href=\"(/jobsearch/jobposting/[^\\\"]+)\"', block)
        if not link_match:
            continue
        link = 'https://www.jobbank.gc.ca' + link_match.group(1).split(';', 1)[0]
        # title
        title_match = re.search(r'<span class=\"noctitle\">\\s*([^<]+)', block)
        title = clean_whitespace(title_match.group(1)) if title_match else 'N/A'
        # company
        company_match = re.search(r'<li class=\"business\">\\s*([^<]+)', block)
        company = clean_whitespace(company_match.group(1)) if company_match else 'Unknown'
        # location
        location_match = re.search(r'<li class=\"location\">[\\s\\S]*?</span>\\s*([^<]+)', block)
        location = clean_whitespace(location_match.group(1)) if location_match else 'Canada'
        # telework
        telework_match = re.search(r'<span class=\"telework\">\\s*([^<]+)', block)
        telework = clean_whitespace(telework_match.group(1)) if telework_match else ''
        # mantém só remoto/telework/híbrido
        if telework and telework.lower() == 'on site':
            continue
        # descrição (fetch da vaga)
        description = strip_html(extract_jobbank_description(link))
        if not description:
            description = f"{title} - {company} - {location}"
        jobs.append({
            'id': f"jobbank-{match.group(1)}",
            'title': title,
            'company': company,
            'link': link,
            'description': description,
            'location': location,
            'pt_hint': has_portuguese_hint(description),
            'source': 'jobbank'
        })
        if len(jobs) >= 200:
            break
except Exception:
    pass

# Landing.jobs (API)
print("  → Landing.jobs...")
try:
    country_map = {
        'US': 'United States',
        'CA': 'Canada',
        'GB': 'United Kingdom',
        'UK': 'United Kingdom',
        'PT': 'Portugal',
        'ES': 'Spain',
        'FR': 'France',
        'DE': 'Germany',
        'NL': 'Netherlands',
        'SE': 'Sweden',
        'DK': 'Denmark',
        'IE': 'Ireland',
        'IT': 'Italy',
        'CH': 'Switzerland',
        'AT': 'Austria',
        'PL': 'Poland',
        'CZ': 'Czech Republic',
    }
    r = requests.get('https://landing.jobs/api/v1/jobs', timeout=20)
    data = r.json() if r.ok else []
    for item in data[:60]:
        locs = item.get('locations') or []
        loc = ''
        if locs and isinstance(locs, list):
            first = locs[0]
            code = (first.get('country_code') or '').upper()
            city = first.get('city') or ''
            country_name = country_map.get(code, code)
            loc = f"{city} ({country_name})" if city else country_name
        else:
            loc = 'Remote' if item.get('remote') else ''
        description = strip_html(item.get('role_description') or item.get('main_requirements') or '')[:800]
        if not is_allowed_location(loc, description):
            continue
        jobs.append({
            'id': item.get('id', item.get('url', '')),
            'title': item.get('title', 'N/A'),
            'company': item.get('company_name', 'Unknown'),
            'link': item.get('url', ''),
            'description': description,
            'location': loc,
            'pt_hint': has_portuguese_hint(description),
            'source': 'landing.jobs'
        })
except Exception:
    pass

# Working Nomads (RSS)
print("  → Working Nomads...")
try:
    feed = feedparser.parse('https://www.workingnomads.com/jobs.rss')
    for entry in feed.entries[:30]:
        summary = strip_html(entry.get('summary', ''))[:800]
        title = entry.get('title', '')
        location = entry.get('location', '') or title
        if not is_allowed_location(location, summary):
            continue
        jobs.append({
            'id': entry.get('id', entry.get('link', '')),
            'title': title or 'N/A',
            'company': entry.get('author', 'Unknown'),
            'link': entry.get('link', ''),
            'description': summary,
            'location': location,
            'pt_hint': has_portuguese_hint(summary),
            'source': 'workingnomads'
        })
except Exception:
    pass

# Jobicy (API)
print("  → Jobicy...")
try:
    r = requests.get('https://jobicy.com/api/v2/remote-jobs?count=50', timeout=20)
    data = r.json() if r.ok else {}
    for item in (data.get('jobs') or [])[:50]:
        location = item.get('jobGeo', '') or item.get('jobLocation', '')
        description = strip_html(item.get('jobExcerpt') or item.get('jobDescription') or '')[:800]
        if not is_allowed_location(location, description):
            continue
        jobs.append({
            'id': item.get('id', item.get('jobUrl', '')),
            'title': item.get('jobTitle', 'N/A'),
            'company': item.get('companyName', 'Unknown'),
            'link': item.get('jobUrl', ''),
            'description': description,
            'location': location,
            'pt_hint': has_portuguese_hint(description),
            'source': 'jobicy'
        })
except Exception:
    pass

# Salva
with open('/tmp/jobs_discovered.json', 'w') as f:
    json.dump(jobs, f)

print(f"✅ Descobertas: {len(jobs)} vagas")
PYSCRIPT

# 2. Filtra (rejeita óbvios)
echo "🔍 Filtrando..."
python3 << 'PYSCRIPT'
import json
import re
import requests
from link_resolver import resolve_direct_url, is_valid_direct_url

with open('/tmp/jobs_discovered.json') as f:
    jobs = json.load(f)

# Filtros rápidos (sem IA)
REJECT_TERMS = ['us only', 'us residents', 'mlm', 'commission only', 'no experience needed']

filtered = []
for job in jobs:
    text = (job.get('title', '') + ' ' + job.get('description', '')).lower()
    
    # Rejeita óbvios
    reject = any(term in text for term in REJECT_TERMS)
    
    if not reject and len(text) > 50:
        filtered.append(job)

print(f"✅ Filtradas: {len(filtered)} vagas")

# Resolve links diretos (obrigatório) + enriquecer detalhes
def _titlecase_slug(slug: str) -> str:
    return ' '.join([s.capitalize() for s in re.split(r'[-_]+', slug or '') if s])

def enrich_from_greenhouse(job: dict) -> bool:
    url = job.get('link', '')
    m = re.search(r'greenhouse\\.io/([^/]+)/jobs/(\\d+)', url)
    if not m:
        return False
    board, job_id = m.group(1), m.group(2)
    api = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
    try:
        r = requests.get(api, timeout=20)
        if not r.ok:
            return False
        data = r.json()
        title = data.get('title') or job.get('title')
        location = (data.get('location') or {}).get('name') if isinstance(data.get('location'), dict) else data.get('location')
        content = data.get('content') or ''
        # Remove HTML bruto
        content = re.sub(r'<[^>]+>', ' ', content)
        content = re.sub(r'\\s+', ' ', content).strip()
        job['title'] = title or job.get('title')
        job['company'] = data.get('company') or _titlecase_slug(board) or job.get('company', 'Empresa')
        if location:
            job['location'] = location
        if content:
            job['description'] = content
        return True
    except Exception:
        return False

def enrich_from_lever(job: dict) -> bool:
    url = job.get('link', '')
    m = re.search(r'jobs\\.lever\\.co/([^/]+)/([a-z0-9-]+)', url)
    if not m:
        return False
    company, posting = m.group(1), m.group(2)
    api = f"https://api.lever.co/v0/postings/{company}/{posting}?mode=json"
    try:
        r = requests.get(api, timeout=20)
        if not r.ok:
            return False
        data = r.json()
        title = data.get('text') or job.get('title')
        location = (data.get('categories') or {}).get('location')
        content = data.get('description') or data.get('lists') or ''
        if isinstance(content, list):
            content = ' '.join([str(x.get('text', '')) for x in content if isinstance(x, dict)])
        content = re.sub(r'<[^>]+>', ' ', str(content))
        content = re.sub(r'\\s+', ' ', content).strip()
        job['title'] = title or job.get('title')
        job['company'] = _titlecase_slug(company) or job.get('company', 'Empresa')
        if location:
            job['location'] = location
        if content:
            job['description'] = content
        return True
    except Exception:
        return False

def looks_like_listing(text: str) -> bool:
    t = (text or '').lower()
    return any(x in t for x in [
        'current openings', 'create a job alert', 'sent directly to your inbox',
        'view all jobs', 'jobs at', 'open positions'
    ])

resolved = []
# Prioriza links que já são diretos
filtered.sort(key=lambda j: 0 if is_valid_direct_url(j.get('link', '')) else 1)
for job in filtered:
    if job.get('source') == 'weworkremotely':
        continue
    source_url = job.get('link')
    if not source_url:
        continue
    direct_url, status = resolve_direct_url(source_url)
    if not direct_url:
        continue
    # Rejeita links diretos que não parecem vaga individual
    if 'greenhouse.io' in direct_url and '/jobs/' not in direct_url:
        continue
    if 'lever.co' in direct_url and '/jobs/' not in direct_url:
        continue
    job['link'] = direct_url
    # Enriquecer conteúdo quando for Greenhouse/Lever
    if 'greenhouse.io' in direct_url:
        enrich_from_greenhouse(job)
    elif 'lever.co' in direct_url:
        enrich_from_lever(job)
    # Descarta se descrição parece página de listagem
    if looks_like_listing(job.get('description', '')):
        continue
    resolved.append(job)
    if len(resolved) >= 5:
        break

print(f"✅ Links diretos: {len(resolved)} vagas")

with open('/tmp/jobs_filtered.json', 'w') as f:
    json.dump(resolved[:5], f)  # Top 5 pro FREE (com link direto)
PYSCRIPT

# 3. Posta
echo "📲 Postando no Telegram..."
python3 << 'PYSCRIPT'
import json
import os
import requests
import re
from bs4 import BeautifulSoup

with open('/tmp/jobs_filtered.json') as f:
    jobs = json.load(f)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN_FREE') or os.environ.get('TELEGRAM_BOT_TOKEN')
CHANNEL = os.environ.get('TELEGRAM_CHANNEL_FREE') or os.environ.get('TELEGRAM_GROUP_ID')

if not TELEGRAM_TOKEN or not CHANNEL:
    print("❌ TELEGRAM_TOKEN_FREE/TELEGRAM_BOT_TOKEN ou TELEGRAM_CHANNEL_FREE/TELEGRAM_GROUP_ID não configurados")
    raise SystemExit(1)

def clean_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '').strip()

def strip_html(text: str) -> str:
    raw = text or ''
    if '<' not in raw and '>' not in raw:
        return clean_whitespace(raw)
    try:
        soup = BeautifulSoup(raw, 'html.parser')
        return clean_whitespace(soup.get_text(' ', strip=True))
    except Exception:
        return clean_whitespace(raw)

def infer_salary(text: str) -> str:
    t = (text or '').lower()
    money = re.findall(r'(?:usd|us\\$|\\$)\\s?([0-9]{2,3}(?:[,\\.][0-9]{3})+|[0-9]{2,3}k)', t)
    if not money:
        return ''
    raw = money[0].replace(',', '').replace('.', '').lower()
    try:
        if raw.endswith('k'):
            value = int(raw[:-1]) * 1000
        else:
            value = int(raw)
    except Exception:
        return ''
    per_year = any(x in t for x in ['per year', 'year', 'annual', '/year', 'yr', 'a year'])
    per_month = any(x in t for x in ['per month', 'month', '/mo', '/month', 'monthly'])
    if per_month:
        monthly = value
    else:
        monthly = int(value / 12) if per_year or value > 20000 else value
    if monthly < 500:
        return ''
    return f"USD ${monthly:,}/mês"

def normalize_location(loc) -> str:
    if not loc:
        return "Remoto"
    if isinstance(loc, str):
        return clean_whitespace(loc)
    if isinstance(loc, list):
        parts = []
        for item in loc:
            if isinstance(item, dict):
                term = item.get('term') or item.get('label') or ''
                if term:
                    parts.append(term)
            elif isinstance(item, str):
                parts.append(item)
        return clean_whitespace(', '.join(parts)) if parts else "Remoto"
    if isinstance(loc, dict):
        term = loc.get('term') or loc.get('label') or ''
        return clean_whitespace(term) if term else "Remoto"
    return "Remoto"

for i, job in enumerate(jobs, 1):
    pt_hint = job.get('pt_hint')
    pt_line = "\n🗣️ Português possível" if pt_hint else ""
    title = job.get('title', 'Vaga Remota')
    company = job.get('company', 'Empresa')
    location = normalize_location(job.get('location'))
    if location and len(location) > 40:
        location = location[:37] + '...'
    raw_description = (job.get('description', '') or '')
    description = strip_html(raw_description)[:160]
    salary = infer_salary(raw_description)
    salary_line = f"💰 {salary}" if salary else ""
    msg = "\n".join([
        f"🎯 {title}",
        "",
        f"{company}",
        f"📍 {location}",
        salary_line,
        "",
        f"✓ {description}",
        pt_line,
        "",
        f"APLICAR: {job.get('link','')}",
    ]).strip()
    
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            json={'chat_id': CHANNEL, 'text': msg.strip()}
        )
        if resp.ok:
            print(f"✅ Vaga {i} postada")
        else:
            print(f"❌ Erro Telegram ({resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        print(f"❌ Erro: {e}")

PYSCRIPT

echo "✅ CICLO COMPLETO"
