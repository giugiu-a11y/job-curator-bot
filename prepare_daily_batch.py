#!/usr/bin/env python3
import os
import re
import json
import time
import itertools
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import List, Dict

import requests
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import urlparse, unquote

from link_resolver import resolve_direct_url, is_valid_direct_url
from config import AGGREGATOR_DOMAINS, VALID_JOB_DOMAINS

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

HISTORY_URLS = DATA_DIR / "posted_urls.txt"
HISTORY_COMPANIES = DATA_DIR / "posted_companies.txt"
COMPANIES_DB = DATA_DIR / "companies_database.json"

ALLOWED_COUNTRY_TERMS = [
    "united states", "usa", "us", "u.s.",
    "eua", "estados unidos",
    "canada",
    "canada", "canadá",
    "europe", "eu", "eea",
    "united kingdom", "uk", "england", "scotland", "wales", "ireland",
    "reino unido", "inglaterra", "escocia", "escócia", "pais de gales", "país de gales", "irlanda",
    "germany", "france", "spain", "portugal", "italy", "netherlands", "belgium",
    "alemanha", "franca", "frança", "espanha", "italia", "itália", "holanda", "países baixos", "paises baixos", "belgica", "bélgica",
    "sweden", "denmark", "norway", "finland",
    "suecia", "suécia", "dinamarca", "noruega", "finlandia", "finlândia",
    "poland", "austria", "switzerland", "czech", "slovakia", "hungary", "romania", "bulgaria", "greece",
    "polonia", "polônia", "austria", "áustria", "suica", "suíça", "tcheca", "republica tcheca", "república tcheca", "eslovaquia", "eslováquia", "hungria", "romenia", "romênia", "bulgaria", "bulgária", "grecia", "grécia",
    "iceland", "luxembourg", "estonia", "latvia", "lithuania", "croatia", "slovenia", "malta", "cyprus",
    "islandia", "islândia", "luxemburgo", "estonia", "estônia", "letonia", "letônia", "lituania", "lituânia", "croacia", "croácia", "eslovenia", "eslovênia", "malta", "chipre",
    "australia",
    "australia", "austrália",
]

BLOCKED_TERMS = [
    "latin america", "latam", "south america",
    "brazil", "brasil", "mexico", "argentina", "colombia", "chile", "peru",
    "uruguay", "paraguay", "bolivia", "ecuador", "venezuela",
    "guatemala", "costa rica", "panama", "dominican", "puerto rico",
    "india", "philippines", "nigeria", "pakistan", "bangladesh",
]

PORTUGUESE_HINTS = [
    "portuguese", "português", "portugues", "pt-br", "pt br", "pt/br",
    "brazilian portuguese",
]

LISTING_PHRASES = [
    "current openings", "create a job alert", "sent directly to your inbox",
    "view all jobs", "jobs at", "open positions",
]
GENERIC_TITLE_PHRASES = [
    "vagas", "vagas remotas", "jobs", "careers", "openings", "vagas abertas",
    "open positions", "current openings",
]

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
MAX_AGE_HOURS = int(os.environ.get("MAX_AGE_HOURS", "168"))
BRAVE_BUDGET = int(os.environ.get("BRAVE_BUDGET", "60"))
_BRAVE_QUOTA_EXCEEDED = False
_BRAVE_REQUESTS = 0
LLM_DAILY_LIMIT = int(os.environ.get("LLM_DAILY_LIMIT", "2"))
LLM_USAGE_PATH = DATA_DIR / "llm_usage.json"
COMPANIES_SCAN_LIMIT = int(os.environ.get("COMPANIES_SCAN_LIMIT", "50"))
COMPANIES_JOBS_LIMIT = int(os.environ.get("COMPANIES_JOBS_LIMIT", "80"))


def load_env():
    for path in ("/etc/llm.env", "/home/ubuntu/.config/clawdbot/gateway.env", str(Path(__file__).parent / ".env")):
        try:
            if not os.path.exists(path) or not os.access(path, os.R_OK):
                continue
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    v = v.strip()
                    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                        v = v[1:-1]
                    os.environ[k] = v
        except (FileNotFoundError, PermissionError, OSError):
            continue


def load_llm_usage():
    today = datetime.utcnow().date().isoformat()
    if not LLM_USAGE_PATH.exists():
        return {"date": today, "count": 0}
    try:
        data = json.loads(LLM_USAGE_PATH.read_text())
    except Exception:
        return {"date": today, "count": 0}
    if data.get("date") != today:
        return {"date": today, "count": 0}
    return {"date": today, "count": int(data.get("count", 0))}


def save_llm_usage(data):
    LLM_USAGE_PATH.write_text(json.dumps(data) + "\n")


def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def strip_html(text: str) -> str:
    raw = text or ""
    if "<" not in raw and ">" not in raw:
        return clean_whitespace(raw)
    try:
        soup = BeautifulSoup(raw, "html.parser")
        return clean_whitespace(soup.get_text(" ", strip=True))
    except Exception:
        return clean_whitespace(raw)


def parse_datetime(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            # aceita epoch em segundos ou ms
            if value > 1_000_000_000_000:
                return datetime.utcfromtimestamp(value / 1000.0)
            return datetime.utcfromtimestamp(value)
        except Exception:
            return None
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            pass
        try:
            return parsedate_to_datetime(v).replace(tzinfo=None)
        except Exception:
            return None
    return None


def is_recent(value, hours: int = 48) -> bool:
    dt = parse_datetime(value)
    if not dt:
        return True
    delta = datetime.utcnow() - dt
    return delta.total_seconds() <= hours * 3600


def has_portuguese_hint(text: str) -> bool:
    t = (text or "").lower()
    return any(h in t for h in PORTUGUESE_HINTS)


def is_allowed_geo(location: str, description: str) -> bool:
    text = f"{location} {description}".lower()
    if any(t in text for t in BLOCKED_TERMS):
        return False
    if any(t in text for t in ALLOWED_COUNTRY_TERMS):
        return True
    # se não há indicação de país, deixa passar para checagem via LLM
    return not location


def looks_like_listing(text: str) -> bool:
    t = (text or "").lower()
    return any(p in t for p in LISTING_PHRASES)


def is_generic_title(title: str) -> bool:
    t = (title or "").strip().lower()
    if not t:
        return True
    return any(t == p or p in t for p in GENERIC_TITLE_PHRASES)


def looks_like_search_url(url: str) -> bool:
    u = (url or "").lower()
    if "search" in u or "jobs/search" in u or "job-search" in u:
        return True
    if "keyword=" in u or "query=" in u or "q=" in u:
        return True
    return False


def host_has_company_label(company: str, url: str) -> bool:
    if not company or not url:
        return False
    host = urlparse(url).netloc.lower()
    labels = [p for p in host.split(".") if p]
    ck = _company_key(company)
    return ck and any(ck == _company_key(lbl) or ck in _company_key(lbl) for lbl in labels)


def is_company_domain_url(url: str) -> bool:
    if not url:
        return False
    host = urlparse(url).netloc.lower()
    # bloqueia ATS e agregadores conhecidos
    for agg in AGGREGATOR_DOMAINS:
        if agg in host:
            return False
    for ats in VALID_JOB_DOMAINS:
        if ats in host:
            return False
    return True


def is_company_job_url(url: str, company: str = "") -> bool:
    if not url:
        return False
    if not is_company_domain_url(url) and not host_has_company_label(company, url):
        return False
    u = url.lower()
    if looks_like_search_url(u):
        return False
    if any(x in u for x in ["/jobs/", "/job/", "/careers/", "/career/", "/positions/", "/vacancies/"]):
        return True
    return False


def is_allowed_company_listing(url: str, company: str = "") -> bool:
    if not url:
        return False
    if looks_like_search_url(url):
        return False
    # aceita página de carreiras/listagem no domínio da empresa
    if not is_company_domain_url(url) and not host_has_company_label(company, url):
        return False
    u = url.lower()
    return any(x in u for x in ["/careers", "/career", "/jobs", "/vacancies", "/positions"])


def is_allowed_ats_url(url: str, company: str = "") -> bool:
    if not url:
        return False
    host = urlparse(url).netloc.lower()
    if not any(ats in host for ats in VALID_JOB_DOMAINS):
        return False
    if host_has_company_label(company, url) or company_name_in_domain(company, host):
        return True
    # fallback: empresa aparece no path do ATS
    path = urlparse(url).path.lower()
    ck = _company_key(company)
    if ck and ck in _company_key(path):
        return True
    return False


def extract_company_domain_from_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    # tenta JSON-LD JobPosting
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.get_text() or "{}")
        except Exception:
            continue
        if isinstance(data, list):
            items = data
        else:
            items = [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") == "JobPosting":
                org = item.get("hiringOrganization") or {}
                if isinstance(org, dict):
                    url = org.get("url") or org.get("sameAs")
                    if isinstance(url, list):
                        url = url[0] if url else ""
                    if isinstance(url, str) and url:
                        return urlparse(url).netloc.lower()
    # fallback: pega link do site da empresa (logo)
    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        host = urlparse(href).netloc.lower()
        if host and "." in host:
            return host
    return ""


def find_company_job_link(html: str, company_domain: str) -> str:
    if not html or not company_domain:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        host = urlparse(href).netloc.lower()
        if company_domain in host and is_company_job_url(href):
            return href
    return ""


def duckduckgo_search(query: str, limit: int = 5) -> list:
    try:
        url = "https://duckduckgo.com/html/"
        r = requests.get(url, params={"q": query}, timeout=20)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for a in soup.select("a.result__a")[:limit]:
            href = a.get("href") or ""
            if href:
                results.append(href)
        return results
    except Exception:
        return []


def bing_search(query: str, limit: int = 5) -> list:
    try:
        url = "https://www.bing.com/search"
        r = requests.get(url, params={"q": query}, headers={"User-Agent": USER_AGENT}, timeout=20)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for a in soup.select("li.b_algo h2 a")[:limit]:
            href = a.get("href") or ""
            if href:
                results.append(href)
        return results
    except Exception:
        return []


def _company_key(company: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (company or "").lower())


def company_name_in_domain(company: str, domain: str) -> bool:
    if not company or not domain:
        return False
    ck = _company_key(company)
    dk = _company_key(domain)
    return ck and ck in dk


def brave_search_urls(query: str, limit: int = 5) -> list:
    results = brave_search(query, count=limit)
    urls = []
    for item in results or []:
        url = item.get("url") or ""
        if url:
            urls.append(url)
    return urls


def find_company_domain(company: str) -> str:
    if not company:
        return ""
    # Evita gastar Brave aqui; usa apenas heurística simples
    return ""
    return ""


def search_company_job_link(company: str, title: str) -> str:
    if not company or not title:
        return ""
    # Evita consumo de Brave no fallback; sem busca externa
    return ""


def resolve_official_company_link(ats_url: str) -> str:
    if not ats_url:
        return ""
    try:
        r = requests.get(ats_url, headers={"User-Agent": USER_AGENT}, timeout=15)
        if not r.ok:
            return ""
        html = r.text
    except Exception:
        return ""
    company_domain = extract_company_domain_from_html(html)
    if company_domain:
        link = find_company_job_link(html, company_domain)
        if link and is_company_job_url(link):
            return link
        # busca externa no domínio da empresa com o slug da vaga
        title = ""
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            title = clean_whitespace(soup.title.string)
        if title:
            query = f"site:{company_domain} \"{title}\""
            for u in duckduckgo_search(query, limit=3):
                if is_company_job_url(u):
                    return u
    return ""


def is_job_specific_url(url: str) -> bool:
    if not url:
        return False
    u = url.lower()
    if "ashbyhq.com" in u:
        parts = u.split("ashbyhq.com/")[-1].split("/")
        return len([p for p in parts if p]) >= 2
    if "smartrecruiters.com" in u:
        parts = u.split("smartrecruiters.com/")[-1].split("/")
        parts = [p for p in parts if p]
        if len(parts) < 3:
            return False
        return any(ch.isdigit() for ch in parts[-1])
    if "lever.co" in u:
        parts = u.split("jobs.lever.co/")[-1].split("/")
        parts = [p for p in parts if p]
        return len(parts) >= 2
    if "workable.com" in u:
        parts = u.split("workable.com/")[-1].split("/")
        parts = [p for p in parts if p]
        if parts and parts[0] == "search":
            return False
        return len(parts) >= 2
    if "myworkdaysite.com" in u:
        return "/job/" in u or "/jobs/" in u
    if "jobvite.com" in u:
        return "/job/" in u
    if any(x in u for x in ["/jobs/", "/job/", "/position/", "/vacancy/", "/opening/"]):
        return True
    # job board known patterns
    if any(x in u for x in [
        "greenhouse.io", "lever.co", "ashbyhq.com", "smartrecruiters.com",
        "workday.com", "myworkdaysite.com", "myworkdayjobs.com",
        "jobvite.com", "icims.com", "recruitee.com", "breezy.hr",
        "applytojob.com", "workable.com", "bamboohr.com",
        "ultipro.com", "paylocity.com", "jazz.co"
    ]):
        return True
    return False


def normalize_location(loc) -> str:
    if not loc:
        return "Remoto"
    if isinstance(loc, str):
        return clean_whitespace(loc)
    if isinstance(loc, list):
        parts = []
        for item in loc:
            if isinstance(item, dict):
                term = item.get("term") or item.get("label") or ""
                if term:
                    parts.append(term)
            elif isinstance(item, str):
                parts.append(item)
        return clean_whitespace(", ".join(parts)) if parts else "Remoto"
    if isinstance(loc, dict):
        term = loc.get("term") or loc.get("label") or ""
        return clean_whitespace(term) if term else "Remoto"
    return "Remoto"


def _brave_token() -> str:
    return (
        os.environ.get("BRAVE_API_KEY") or
        os.environ.get("BRAVE_SEARCH_API_KEY") or
        os.environ.get("BRAVE_SUBSCRIPTION_TOKEN") or
        ""
    )


def brave_search(query: str, count: int = 10, offset: int = 0) -> list:
    token = _brave_token()
    if not token:
        return []
    global _BRAVE_REQUESTS
    if _BRAVE_REQUESTS >= BRAVE_BUDGET:
        return []
    headers = {"X-Subscription-Token": token}
    params = {
        "q": query,
        "count": count,
        "offset": offset,
        "search_lang": "en",
        "safesearch": "moderate",
    }
    try:
        r = requests.get(BRAVE_ENDPOINT, headers=headers, params=params, timeout=20)
        _BRAVE_REQUESTS += 1
        if r.status_code == 429:
            global _BRAVE_QUOTA_EXCEEDED
            _BRAVE_QUOTA_EXCEEDED = True
            return []
        if not r.ok:
            return []
        data = r.json()
        return data.get("web", {}).get("results", []) if isinstance(data, dict) else []
    except Exception:
        return []


def _parse_domain(url: str) -> str:
    if not url:
        return ""
    u = url.strip()
    if "://" not in u:
        u = "https://" + u
    try:
        return urlparse(u).netloc.lower()
    except Exception:
        return ""


def load_companies_db() -> list:
    if not COMPANIES_DB.exists():
        return []
    try:
        data = json.loads(COMPANIES_DB.read_text())
    except Exception:
        return []
    if isinstance(data, dict):
        items = data.get("companies") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []
    return [i for i in items if isinstance(i, dict)]


def select_companies_subset(companies: list, limit: int) -> list:
    if not companies or limit <= 0:
        return []
    if len(companies) <= limit:
        return companies
    start = int(datetime.utcnow().strftime("%j")) % len(companies)
    return (companies[start:] + companies[:start])[:limit]


def _company_queries(name: str, domain: str) -> list:
    if not name:
        return []
    queries = []
    if domain:
        queries.append(f"site:{domain} (\"/job/\" OR \"/jobs/\" OR \"/careers/\")")
        queries.append(f"site:{domain} (jobs OR careers) \"{name}\"")
    ats_groups = [
        "site:boards.greenhouse.io OR site:job-boards.greenhouse.io OR site:jobs.lever.co OR site:ashbyhq.com OR site:smartrecruiters.com",
        "site:workable.com OR site:myworkdayjobs.com OR site:myworkdaysite.com OR site:jobvite.com OR site:icims.com OR site:recruitee.com OR site:breezy.hr OR site:applytojob.com",
    ]
    for g in ats_groups:
        queries.append(f"\"{name}\" ({g})")
    return queries


def fetch_companies_from_db(limit: int = 80) -> list:
    jobs = []
    if not _brave_token():
        return jobs
    companies = load_companies_db()
    if not companies:
        return jobs
    subset = select_companies_subset(companies, COMPANIES_SCAN_LIMIT)
    seen = set()
    for c in subset:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        careers_url = (c.get("careers_url") or "").strip()
        domain = _parse_domain(careers_url)
        for q in _company_queries(name, domain):
            if _BRAVE_QUOTA_EXCEEDED or _BRAVE_REQUESTS >= BRAVE_BUDGET:
                return jobs
            results = brave_search(q, count=6)
            time.sleep(1.1)
            for item in results:
                url = item.get("url") or ""
                if not url or url in seen:
                    continue
                if looks_like_search_url(url):
                    continue
                if not is_job_specific_url(url):
                    continue
                if not (is_allowed_ats_url(url, name) or is_company_job_url(url, name)):
                    continue
                seen.add(url)
                jobs.append({
                    "id": f"company-{hash(url)}",
                    "title": item.get("title") or "N/A",
                    "company": name,
                    "description": strip_html(item.get("description") or "")[:1200],
                    "source_url": url,
                    "location": "",
                    "source": "companies-db",
                    "pt_hint": has_portuguese_hint(item.get("description") or ""),
                })
                if len(jobs) >= limit:
                    return jobs
    return jobs


def fetch_brave_direct(limit=30):
    jobs = []
    if not _brave_token():
        return jobs
    if _BRAVE_QUOTA_EXCEEDED:
        return jobs
    countries = [
        "United States", "Canada", "United Kingdom", "Germany", "France",
        "Netherlands", "Spain", "Portugal", "Ireland", "Sweden",
        "Denmark", "Norway", "Finland", "Australia"
    ]
    sectors = [
        "engineering", "developer", "data", "design",
        "marketing", "sales", "operations", "customer support",
        "healthcare", "nurse", "accountant", "finance", "product",
        "hr", "legal", "education", "teacher", "analyst", "project manager"
    ]
    domains = [
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
        "jobs.lever.co",
        "ashbyhq.com",
        "smartrecruiters.com",
        "workable.com",
        "myworkdayjobs.com",
        "myworkdaysite.com",
        "jobvite.com",
        "icims.com",
        "recruitee.com",
        "breezy.hr",
        "applytojob.com",
        "bamboohr.com",
        "ultipro.com",
        "paylocity.com",
        "jazz.co",
    ]
    fixed_queries = [
        "site:boards.greenhouse.io \"/jobs/\" remote United States",
        "site:boards.greenhouse.io \"/jobs/\" remote Canada",
        "site:boards.greenhouse.io \"/jobs/\" remote United Kingdom",
        "site:boards.greenhouse.io \"/jobs/\" remote Germany",
        "site:boards.greenhouse.io \"/jobs/\" remote France",
        "site:boards.greenhouse.io \"/jobs/\" remote Spain",
        "site:boards.greenhouse.io \"/jobs/\" remote Portugal",
        "site:jobs.lever.co remote United States",
        "site:jobs.lever.co remote Canada",
        "site:jobs.lever.co remote United Kingdom",
    ]
    queries = []
    for c in countries:
        queries.append(f"site:boards.greenhouse.io \"/jobs/\" remote {c}")
    for s in sectors:
        queries.append(f"site:boards.greenhouse.io \"/jobs/\" remote {s}")
    for c in countries:
        queries.append(f"site:jobs.lever.co remote {c}")
    for s in sectors:
        queries.append(f"site:jobs.lever.co remote {s}")
    # fallback for other ATS
    for c in countries:
        queries.append(f"site:ashbyhq.com jobs remote {c}")
        queries.append(f"site:smartrecruiters.com jobs remote {c}")
        queries.append(f"site:workable.com jobs remote {c}")
        queries.append(f"site:myworkdayjobs.com jobs {c}")
        queries.append(f"site:myworkdaysite.com jobs {c}")
        queries.append(f"site:jobvite.com jobs {c}")
        queries.append(f"site:icims.com jobs {c}")
        queries.append(f"site:recruitee.com jobs {c}")
        queries.append(f"site:breezy.hr jobs {c}")
        queries.append(f"site:applytojob.com jobs {c}")
        queries.append(f"site:bamboohr.com jobs {c}")
        queries.append(f"site:ultipro.com jobs {c}")
        queries.append(f"site:paylocity.com jobs {c}")
        queries.append(f"site:jazz.co jobs {c}")
    for s in sectors:
        queries.append(f"site:myworkdayjobs.com {s}")
        queries.append(f"site:myworkdaysite.com {s}")
        queries.append(f"site:jobvite.com {s}")
        queries.append(f"site:icims.com {s}")
        queries.append(f"site:recruitee.com {s}")
        queries.append(f"site:breezy.hr {s}")
        queries.append(f"site:applytojob.com {s}")
        queries.append(f"site:bamboohr.com {s}")
        queries.append(f"site:ultipro.com {s}")
        queries.append(f"site:paylocity.com {s}")
        queries.append(f"site:jazz.co {s}")
    for c in countries:
        queries.append(f"site:boards.greenhouse.io jobs hybrid {c}")
        queries.append(f"site:jobs.lever.co hybrid {c}")
        queries.append(f"site:boards.greenhouse.io jobs onsite {c}")
        queries.append(f"site:jobs.lever.co onsite {c}")
    for c in countries:
        queries.append(f"site:boards.greenhouse.io visa sponsorship {c}")
        queries.append(f"site:jobs.lever.co visa sponsorship {c}")
        queries.append(f"site:myworkdayjobs.com visa sponsorship {c}")
        queries.append(f"site:jobvite.com visa sponsorship {c}")
        queries.append(f"site:icims.com visa sponsorship {c}")
        queries.append(f"site:recruitee.com visa sponsorship {c}")
    # limita número de queries para controlar tempo
    max_queries = int(os.environ.get("BRAVE_QUERY_LIMIT", "40"))
    if len(queries) > max_queries:
        start = int(datetime.utcnow().strftime("%j")) % len(queries)
        queries = (queries[start:] + queries[:start])[:max_queries]
    queries = fixed_queries + queries
    seen = set()
    domain_counts = {}
    total_found = 0
    for q in queries:
        results = brave_search(q, count=10)
        total_found += len(results)
        time.sleep(1.2)
        for item in results:
            url = item.get("url") or ""
            if not url or url in seen:
                continue
            if "boards.greenhouse.io/embed/" in url:
                continue
            if not any(d in url for d in domains):
                continue
            if not is_job_specific_url(url):
                continue
            domain = url.split("/")[2] if "://" in url else ""
            if domain:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
                if domain_counts[domain] > 25:
                    continue
            seen.add(url)
            jobs.append({
                "id": f"brave-{hash(url)}",
                "title": item.get("title") or "N/A",
                "company": item.get("source") or "Unknown",
                "description": strip_html(item.get("description") or "")[:1200],
                "source_url": url,
                "location": "",
                "source": "brave",
                "pt_hint": has_portuguese_hint(item.get("description") or ""),
            })
            if len(jobs) >= limit:
                print(f"Brave results total: {total_found}, kept: {len(jobs)}")
                return jobs
    print(f"Brave results total: {total_found}, kept: {len(jobs)}")
    return jobs


def fallback_search_direct(job: Dict) -> str:
    if not _brave_token():
        return ""
    company = (job.get("company") or "").strip()
    title = (job.get("title") or "").strip()
    if not company or not title:
        return ""
    query = (
        f"\"{company}\" \"{title}\" "
        "site:greenhouse.io OR site:lever.co OR site:ashbyhq.com OR "
        "site:workday.com OR site:myworkdaysite.com OR site:jobvite.com OR "
        "site:smartrecruiters.com OR site:icims.com OR site:workable.com OR "
        "site:recruitee.com OR site:breezy.hr OR site:applytojob.com"
    )
    results = brave_search(query, count=5)
    time.sleep(2)
    for item in results:
        url = item.get("url") or ""
        if not url:
            continue
        if is_valid_direct_url(url):
            return url
    return ""


def fetch_remotive(limit=50):
    jobs = []
    r = requests.get("https://remotive.com/api/remote-jobs", timeout=20)
    if not r.ok:
        return jobs
    data = r.json()
    for item in (data.get("jobs") or [])[:limit]:
        desc = strip_html(item.get("description") or "")[:1200]
        loc = item.get("candidate_required_location", "") or item.get("location", "")
        jobs.append({
            "id": f"remotive-{item.get('id')}",
            "title": item.get("title") or "N/A",
            "company": item.get("company_name") or "Unknown",
            "description": desc,
            "source_url": item.get("url") or "",
            "location": loc,
            "source": "remotive",
            "pt_hint": has_portuguese_hint(desc),
            "posted_at": item.get("publication_date"),
        })
    return jobs


def fetch_remoteok(limit=50):
    jobs = []
    r = requests.get("https://remoteok.com/api", timeout=20)
    if not r.ok:
        return jobs
    data = r.json()
    for item in data[1:limit+1]:
        desc = strip_html(item.get("description") or "")[:1200]
        loc = item.get("location") or ""
        jobs.append({
            "id": f"remoteok-{item.get('id')}",
            "title": item.get("position") or "N/A",
            "company": item.get("company") or "Unknown",
            "description": desc,
            "source_url": item.get("url") or "",
            "location": loc,
            "source": "remoteok",
            "pt_hint": has_portuguese_hint(desc),
            "posted_at": item.get("date") or item.get("epoch"),
        })
    return jobs


def fetch_himalayas(limit=50):
    jobs = []
    feed = feedparser.parse("https://himalayas.app/rss")
    for entry in feed.entries[:limit]:
        desc = strip_html(entry.get("summary") or "")[:1200]
        loc = entry.get("location") or entry.get("tags") or ""
        jobs.append({
            "id": f"himalayas-{entry.get('id', entry.get('link',''))}",
            "title": entry.get("title") or "N/A",
            "company": entry.get("author") or "Unknown",
            "description": desc,
            "source_url": entry.get("link") or "",
            "location": loc,
            "source": "himalayas",
            "pt_hint": has_portuguese_hint(desc),
            "posted_at": entry.get("published") or entry.get("updated"),
        })
    return jobs


def fetch_jobicy(limit=50):
    jobs = []
    r = requests.get("https://jobicy.com/api/v2/remote-jobs?count=50", timeout=20)
    if not r.ok:
        return jobs
    data = r.json()
    for item in (data.get("jobs") or [])[:limit]:
        desc = strip_html(item.get("jobExcerpt") or item.get("jobDescription") or "")[:1200]
        loc = item.get("jobGeo") or item.get("jobLocation") or ""
        jobs.append({
            "id": f"jobicy-{item.get('id')}",
            "title": item.get("jobTitle") or "N/A",
            "company": item.get("companyName") or "Unknown",
            "description": desc,
            "source_url": item.get("jobUrl") or "",
            "location": loc,
            "source": "jobicy",
            "pt_hint": has_portuguese_hint(desc),
            "posted_at": item.get("jobPublicationDate") or item.get("pubDate"),
        })
    return jobs


def fetch_workingnomads(limit=50):
    jobs = []
    feed = feedparser.parse("https://www.workingnomads.com/jobs.rss")
    for entry in feed.entries[:limit]:
        desc = strip_html(entry.get("summary") or "")[:1200]
        loc = entry.get("location") or entry.get("tags") or ""
        jobs.append({
            "id": f"workingnomads-{entry.get('id', entry.get('link',''))}",
            "title": entry.get("title") or "N/A",
            "company": entry.get("author") or "Unknown",
            "description": desc,
            "source_url": entry.get("link") or "",
            "location": loc,
            "source": "workingnomads",
            "pt_hint": has_portuguese_hint(desc),
            "posted_at": entry.get("published") or entry.get("updated"),
        })
    return jobs


def fetch_landingjobs(limit=50):
    jobs = []
    r = requests.get("https://landing.jobs/api/v1/jobs", timeout=20)
    if not r.ok:
        return jobs
    data = r.json()
    for item in data[:limit]:
        desc = strip_html(item.get("role_description") or item.get("main_requirements") or "")[:1200]
        loc = "Remote" if item.get("remote") else ""
        locs = item.get("locations") or []
        if locs:
            first = locs[0]
            city = first.get("city") or ""
            code = (first.get("country_code") or "").upper()
            loc = f"{city} ({code})" if city else code
        jobs.append({
            "id": f"landingjobs-{item.get('id')}",
            "title": item.get("title") or "N/A",
            "company": item.get("company_name") or "Unknown",
            "description": desc,
            "source_url": item.get("url") or "",
            "location": loc,
            "source": "landingjobs",
            "pt_hint": has_portuguese_hint(desc),
            "posted_at": item.get("published_at") or item.get("created_at"),
        })
    return jobs


def fetch_weworkremotely(limit=50):
    jobs = []
    feeds = [
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
    per_feed = max(5, limit // len(feeds))
    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
        except Exception:
            continue
        for entry in feed.entries[:per_feed]:
            title = entry.get("title") or ""
            company = "Unknown"
            if ":" in title:
                parts = title.split(":", 1)
                company = parts[0].strip() or "Unknown"
                title = parts[1].strip() or title
            desc = strip_html(entry.get("description") or entry.get("summary") or "")[:1200]
            jobs.append({
                "id": f"weworkremotely-{entry.get('id', entry.get('link',''))}",
                "title": title or "N/A",
                "company": company,
                "description": desc,
                "source_url": entry.get("link") or "",
                "location": "Remote",
                "source": "weworkremotely",
                "pt_hint": has_portuguese_hint(desc),
                "posted_at": entry.get("published") or entry.get("updated"),
            })
        if len(jobs) >= limit:
            break
    return jobs[:limit]


def enrich_greenhouse(job: Dict) -> None:
    url = job.get("direct_url", "")
    m = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if not m:
        return
    board, job_id = m.group(1), m.group(2)
    api = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
    r = requests.get(api, timeout=20)
    if not r.ok:
        return
    data = r.json()
    job["title"] = data.get("title") or job.get("title")
    job["company"] = data.get("company") or board
    location = data.get("location")
    if isinstance(location, dict):
        job["location"] = location.get("name") or job.get("location")
    content = data.get("content") or ""
    content = strip_html(content)
    if content:
        job["description"] = content


def enrich_lever(job: Dict) -> None:
    url = job.get("direct_url", "")
    m = re.search(r"jobs\.lever\.co/([^/]+)/([a-z0-9-]+)", url)
    if not m:
        return
    company, posting = m.group(1), m.group(2)
    api = f"https://api.lever.co/v0/postings/{company}/{posting}?mode=json"
    r = requests.get(api, timeout=20)
    if not r.ok:
        return
    data = r.json()
    job["title"] = data.get("text") or job.get("title")
    job["company"] = company
    loc = (data.get("categories") or {}).get("location")
    if loc:
        job["location"] = loc
    content = data.get("description") or ""
    content = strip_html(content)
    if content:
        job["description"] = content


def infer_company_from_url(url: str) -> str:
    u = (url or "").lower()
    def _titlecase(s: str) -> str:
        return " ".join([p.capitalize() for p in re.split(r"[-_]+", s) if p])
    if "ashbyhq.com/" in u:
        parts = u.split("ashbyhq.com/")[-1].split("/")
        return _titlecase(parts[0]) if parts and parts[0] else ""
    if "smartrecruiters.com/" in u:
        parts = u.split("smartrecruiters.com/")[-1].split("/")
        return _titlecase(parts[0]) if parts and parts[0] else ""
    if "breezy.hr/p/" in u:
        parts = u.split("breezy.hr/p/")[-1].split("-")
        return _titlecase(parts[0]) if parts and parts[0] else ""
    return ""


def infer_company_from_direct_url(url: str) -> str:
    u = (url or "").lower()
    def _titlecase(s: str) -> str:
        return " ".join([p.capitalize() for p in re.split(r"[-_]+", s) if p])
    def _titlecase(s: str) -> str:
        return " ".join([p.capitalize() for p in re.split(r"[-_]+", s) if p])
    m = re.search(r"greenhouse\.io/([^/]+)/jobs/\d+", u)
    if m:
        return _titlecase(m.group(1))
    m = re.search(r"jobs\.lever\.co/([^/]+)/", u)
    if m:
        return _titlecase(m.group(1))
    if "ashbyhq.com/" in u:
        parts = u.split("ashbyhq.com/")[-1].split("/")
        return _titlecase(parts[0]) if parts and parts[0] else ""
    if "smartrecruiters.com/" in u:
        parts = u.split("smartrecruiters.com/")[-1].split("/")
        return _titlecase(parts[0]) if parts and parts[0] else ""
    if "recruitee.com/o/" in u:
        parts = u.split("recruitee.com/")[-1].split("/")
        return _titlecase(parts[0]) if parts and parts[0] else ""
    if ".recruitee.com/" in u:
        host = u.split("://")[-1].split("/")[0]
        sub = host.split(".")[0]
        return _titlecase(sub) if sub else ""
    if "breezy.hr/p/" in u:
        parts = u.split("breezy.hr/p/")[-1].split("-")
        return _titlecase(parts[0]) if parts and parts[0] else ""
    if ".myworkdayjobs.com" in u:
        host = u.split("://")[-1].split("/")[0]
        sub = host.split(".")[0]
        return _titlecase(sub) if sub else ""
    if "myworkdaysite.com/" in u and "/recruiting/" in u:
        tail = u.split("/recruiting/")[-1]
        parts = [p for p in tail.split("/") if p]
        if parts:
            return _titlecase(parts[0])
    if "jobs.jobvite.com/" in u:
        tail = u.split("jobs.jobvite.com/")[-1]
        parts = [p for p in tail.split("/") if p]
        if parts:
            return _titlecase(parts[0])
    if "apply.workable.com/" in u:
        parts = u.split("apply.workable.com/")[-1].split("/")
        return _titlecase(parts[0]) if parts and parts[0] else ""
    if "jobs.workable.com/view/" in u:
        tail = u.split("jobs.workable.com/view/")[-1]
        if "-at-" in tail:
            company = tail.split("-at-")[-1].split("/")[0]
            return _titlecase(company)
    return ""


def clean_company_name(name: str) -> str:
    if not name:
        return ""
    n = unquote(name).replace("%20", " ").strip()
    n = re.sub(r"\s+", " ", n)
    return n


def load_history(path: Path) -> set:
    if not path.exists():
        return set()
    with open(path, "r") as f:
        return set([line.strip() for line in f if line.strip()])


def save_history(path: Path, items: List[str]) -> None:
    with open(path, "a") as f:
        for item in items:
            f.write(item + "\n")


def build_llm_payload(jobs: List[Dict]) -> str:
    entries = []
    for i, j in enumerate(jobs):
        entries.append(
            f"=== VAGA {i} ===\n"
            f"TITULO: {j.get('title','N/A')}\n"
            f"EMPRESA: {j.get('company','N/A')}\n"
            f"LOCALIZACAO: {normalize_location(j.get('location'))}\n"
            f"LINK: {j.get('direct_url','')}\n"
            f"DESCRICAO: {j.get('description','')[:600]}"
        )
    return "\n".join(entries)


def call_gemini(text: str, count: int) -> List[Dict]:
    api_key = os.environ.get("GOOGLE_API_KEY") or ""
    model = os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash-lite"
    prompt = f"""
Você é um curador especialista em vagas internacionais para brasileiros. Analise CADA vaga abaixo e retorne JSON ARRAY na mesma ordem.

REGRAS:
- Países permitidos: EUA, Canadá, Europa (múltiplos países), Austrália.
- Proibido: Brasil, LATAM, Índia, Filipinas, etc.
- Marque como aprovada apenas se não exigir cidadania específica e aceitar candidatos internacionais.
- Se o país não for explícito e não estiver na lista permitida, marque como reprovada.
- Nunca use \"Worldwide\" ou \"Global\" em pais; use um país específico permitido.
- Se o inglês não for explicitamente exigido, use \"intermediario\". Se a vaga for de suporte/atendimento e não houver exigência explícita, use \"basico\".
- Se a vaga não menciona faculdade, use \"nao_importa\".
- Se a vaga não menciona experiência, use 0.
- Sempre preencha salario_mensal (valor mensal) e moeda ("USD","CAD","EUR","GBP","AUD").
- salario_estimado deve ser true/false.
- Gere titulo e descricao em português.

FORMATO EXATO:
[
  {{
    "job_index": 0,
    "aprovada": true/false,
    "motivo_rejeicao": "..." ou null,
    "titulo": "...",
    "empresa": "...",
    "pais": "...",
    "setor": "saude|exatas|humanas|artes|tech|business",
    "salario_mensal": 5000,
    "moeda": "USD",
    "salario_estimado": true/false,
    "requisitos": {{
      "ingles": "fluente|intermediario|basico|nao_precisa",
      "faculdade": "sim|nao|nao_importa",
      "experiencia_anos": 0|2|5|10,
      "descricao": "1 linha"
    }},
    "internacional_ok": true/false
  }}
]
""".strip()

    if not api_key:
        raise ValueError("GOOGLE_API_KEY não configurada")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt + "\\n\\n" + text}]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096,
            "response_mime_type": "application/json"
        }
    }
    data = None
    last_err = None
    for attempt in range(3):
        r = requests.post(url, json=body, timeout=60)
        if r.ok:
            data = r.json()
            break
        last_err = f"Gemini HTTP {r.status_code}: {r.text[:200]}"
        if r.status_code in (429, 503):
            time.sleep(5 + attempt * 5)
            continue
        break
    if data is None:
        raise ValueError(last_err or "Gemini request failed")
    cand = (data.get("candidates") or [{}])[0]
    parts = ((cand.get("content") or {}).get("parts") or [])
    text_out = parts[0].get("text") if parts else ""
    if not text_out:
        raise ValueError("Gemini resposta vazia")
    text_out = text_out.strip()
    if text_out.startswith("```"):
        text_out = text_out.strip("`")
        text_out = text_out.replace("json", "", 1).strip()
    try:
        result = json.loads(text_out)
    except Exception:
        start = text_out.find('[')
        end = text_out.rfind(']')
        chunk = text_out
        if start != -1 and end != -1 and end > start:
            chunk = text_out[start:end+1]
        try:
            result = json.loads(chunk)
        except Exception:
            import ast
            result = ast.literal_eval(chunk)
    if not isinstance(result, list):
        preview = text_out[:500].replace("\\n", " ")
        raise ValueError(f"Gemini result is not a list: {type(result)} | raw: {preview}")
    return result


def validate_diversity(items: List[Dict]) -> bool:
    countries = set(i.get("pais", "").lower() for i in items)
    sectors = set(i.get("setor", "") for i in items)
    has_faculdade = any(i.get("requisitos", {}).get("faculdade") == "sim" for i in items)
    has_no_faculdade = any(i.get("requisitos", {}).get("faculdade") == "nao" for i in items)
    has_no_english = any(i.get("requisitos", {}).get("ingles") in ("basico", "nao_precisa") for i in items)
    has_no_exp = any(i.get("requisitos", {}).get("experiencia_anos") == 0 for i in items)
    has_exp = any((i.get("requisitos", {}).get("experiencia_anos") or 0) >= 2 for i in items)
    all_intern = all(i.get("internacional_ok") for i in items)
    companies = [clean_whitespace(i.get("empresa", "")).lower() for i in items]
    unique_companies = len(set([c for c in companies if c])) == len([c for c in companies if c])
    return (
        len(countries) >= 2 and
        len(sectors) >= 3 and
        has_faculdade and
        has_no_faculdade and
        has_no_english and
        has_no_exp and
        has_exp and
        all_intern and
        unique_companies
    )


def llm_country_allowed(pais: str) -> bool:
    p = (pais or "").lower()
    if not p:
        return False
    if "worldwide" in p or "global" in p or "anywhere" in p:
        return False
    if any(t in p for t in BLOCKED_TERMS):
        return False
    return any(t in p for t in ALLOWED_COUNTRY_TERMS)


def infer_country_from_location(loc: str) -> str:
    t = (loc or "").lower()
    mapping = [
        ("united states", "USA"),
        ("usa", "USA"),
        ("u.s.", "USA"),
        ("canada", "Canada"),
        ("united kingdom", "United Kingdom"),
        ("uk", "United Kingdom"),
        ("england", "United Kingdom"),
        ("ireland", "Ireland"),
        ("germany", "Germany"),
        ("france", "France"),
        ("netherlands", "Netherlands"),
        ("spain", "Spain"),
        ("portugal", "Portugal"),
        ("italy", "Italy"),
        ("sweden", "Sweden"),
        ("denmark", "Denmark"),
        ("norway", "Norway"),
        ("finland", "Finland"),
        ("poland", "Poland"),
        ("austria", "Austria"),
        ("switzerland", "Switzerland"),
        ("australia", "Australia"),
    ]
    for key, val in mapping:
        if key in t:
            return val
    return ""


def select_diverse_batch(items: List[Dict], size: int = 5) -> List[Dict]:
    # tenta combinações nas primeiras 30 vagas aprovadas
    approved = [i for i in items if i.get("aprovada")]
    pool = approved[:50]
    for combo in itertools.combinations(pool, size):
        if validate_diversity(list(combo)):
            return list(combo)
    return []


def pick_with_requirements(items: List[Dict], size: int) -> List[Dict]:
    if not items:
        return []
    picked = []
    used = set()

    def _pick_one(predicate):
        for i, it in enumerate(items):
            if i in used:
                continue
            if predicate(it):
                used.add(i)
                picked.append(it)
                return True
        return False

    _pick_one(lambda it: it.get("requisitos", {}).get("faculdade") == "nao")
    _pick_one(lambda it: it.get("requisitos", {}).get("ingles") in ("basico", "nao_precisa"))

    for i, it in enumerate(items):
        if i in used:
            continue
        picked.append(it)
        used.add(i)
        if len(picked) >= size:
            break
    return picked[:size]


def _base_domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host
    except Exception:
        return ""


def interleave_by_domain(items: List[Dict]) -> List[Dict]:
    buckets = {}
    for item in items:
        url = item.get("direct_url") or ""
        key = _base_domain(url)
        buckets.setdefault(key, []).append(item)
    order = []
    while True:
        added = False
        for key in list(buckets.keys()):
            if buckets[key]:
                order.append(buckets[key].pop(0))
                added = True
            if not buckets[key]:
                buckets.pop(key, None)
        if not added:
            break
    return order


def is_ats_url(url: str) -> bool:
    if not url:
        return False
    host = urlparse(url).netloc.lower()
    return any(ats in host for ats in VALID_JOB_DOMAINS)


def currency_for_country(country: str) -> str:
    c = (country or "").lower()
    if "canada" in c:
        return "CAD"
    if "united kingdom" in c or "uk" in c or "reino unido" in c:
        return "GBP"
    if any(x in c for x in ["germany", "france", "spain", "portugal", "italy", "netherlands", "belgium",
                            "sweden", "denmark", "norway", "finland", "poland", "austria", "switzerland",
                            "czech", "slovakia", "hungary", "romania", "bulgaria", "greece", "iceland",
                            "luxembourg", "estonia", "latvia", "lithuania", "croatia", "slovenia", "malta", "cyprus",
                            "alemanha", "frança", "espanha", "portugal", "itália", "holanda", "bélgica",
                            "suecia", "dinamarca", "noruega", "finlândia", "polônia", "áustria", "suíça",
                            "república tcheca", "eslováquia", "romênia", "bulgária", "grécia", "islândia",
                            "luxemburgo", "estônia", "letônia", "lituânia", "croácia", "eslovênia", "malta", "chipre"]):
        return "EUR"
    if "australia" in c or "austrália" in c:
        return "AUD"
    return "USD"


def _level_from_title(title: str) -> str:
    t = (title or "").lower()
    if any(k in t for k in ["cto", "chief", "director", "vp", "head of", "principal", "staff", "lead architect"]):
        return "exec"
    if any(k in t for k in ["senior", "sr.", "lead", "manager", "tech lead", "líder", "gerente"]):
        return "senior"
    if any(k in t for k in ["junior", "jr.", "estagi", "intern", "trainee"]):
        return "junior"
    return "mid"


def _role_bucket(title: str) -> str:
    t = (title or "").lower()
    if any(k in t for k in ["data scientist", "machine learning", "ml", "ai", "engenheiro de dados", "cientista de dados"]):
        return "data"
    if any(k in t for k in ["software", "engenheiro", "developer", "fullstack", "backend", "frontend"]):
        return "eng"
    if any(k in t for k in ["product", "produto"]):
        return "product"
    if any(k in t for k in ["design", "designer", "ux", "ui"]):
        return "design"
    if any(k in t for k in ["marketing", "growth", "seo", "content", "redator"]):
        return "marketing"
    if any(k in t for k in ["finance", "financial", "controller", "controll", "fp&a", "accountant"]):
        return "finance"
    if any(k in t for k in ["support", "suporte", "customer", "atendimento"]):
        return "support"
    return "general"


def _country_multiplier(country: str) -> float:
    c = (country or "").lower()
    if "united states" in c or "usa" in c or "u.s." in c:
        return 1.0
    if "canada" in c:
        return 0.9
    if "united kingdom" in c or "uk" in c:
        return 0.85
    if any(x in c for x in ["germany", "france", "spain", "portugal", "italy", "netherlands", "belgium",
                            "sweden", "denmark", "norway", "finland", "poland", "austria", "switzerland"]):
        return 0.85
    if "australia" in c:
        return 0.9
    return 0.9


def infer_salary_mensal(exp_anos: int, setor: str) -> int:
    exp = exp_anos or 0
    base = 3000
    if exp >= 10:
        base = 10000
    elif exp >= 5:
        base = 7000
    elif exp >= 2:
        base = 4500
    else:
        base = 3000
    if setor in ("saude", "tech"):
        base = int(base * 1.1)
    return base


def infer_salary_from_title(title: str, country: str, setor: str, exp_anos: int) -> int:
    level = _level_from_title(title)
    role = _role_bucket(title)
    base_map = {
        "eng": {"junior": 3500, "mid": 5500, "senior": 8000, "exec": 12000},
        "data": {"junior": 3800, "mid": 6000, "senior": 9000, "exec": 13000},
        "product": {"junior": 3200, "mid": 5200, "senior": 7800, "exec": 11000},
        "design": {"junior": 2800, "mid": 4500, "senior": 6500, "exec": 9000},
        "marketing": {"junior": 2500, "mid": 4000, "senior": 6000, "exec": 8500},
        "finance": {"junior": 3000, "mid": 4800, "senior": 7000, "exec": 10000},
        "support": {"junior": 2200, "mid": 3200, "senior": 4500, "exec": 6500},
        "general": {"junior": 2600, "mid": 4000, "senior": 5800, "exec": 8500},
    }
    base = base_map.get(role, base_map["general"]).get(level, 4000)
    # ajuste por experiência quando disponível
    if exp_anos >= 5 and base < 6000:
        base = int(base * 1.2)
    if exp_anos >= 10:
        base = int(base * 1.3)
    if setor in ("saude", "tech"):
        base = int(base * 1.05)
    base = int(base * _country_multiplier(country))
    return base


def format_money(value) -> str:
    try:
        v = float(value)
    except Exception:
        return ""
    if v >= 1000:
        return f"{int(round(v)):,}".replace(",", ".")
    return f"{v:.0f}"


def format_post(job: Dict) -> str:
    a = job.get("analysis", {})
    titulo = a.get("titulo") or job.get("title") or "Vaga"
    empresa = a.get("empresa") or job.get("company") or "Empresa"
    pais = a.get("pais") or "Local"
    salario = a.get("salario_mensal") or a.get("salario_usd_mes") or None
    salario_estimado = bool(a.get("salario_estimado"))
    if not salario:
        exp = (a.get("requisitos") or {}).get("experiencia_anos") or 0
        setor = a.get("setor") or ""
        salario = infer_salary_from_title(titulo, pais, setor, exp)
        salario_estimado = True
    else:
        # se salário vier muito baixo para cargos seniores, ajusta
        level = _level_from_title(titulo)
        if level in ("senior", "exec") and int(salario) < 4000:
            exp = (a.get("requisitos") or {}).get("experiencia_anos") or 5
            setor = a.get("setor") or ""
            salario = infer_salary_from_title(titulo, pais, setor, exp)
            salario_estimado = True
    moeda = a.get("moeda") or currency_for_country(pais)
    symbol = {
        "USD": "USD",
        "CAD": "CAD",
        "EUR": "EUR",
        "GBP": "GBP",
        "AUD": "AUD",
    }.get(moeda, moeda)
    value = format_money(salario)
    requisito = (a.get("requisitos", {}) or {}).get("descricao") or ""
    if not requisito:
        requisito = "Oportunidade internacional com possibilidade de crescimento"
    link = job.get("direct_url") or ""
    prefix = "~" if salario_estimado else ""
    return (
        f"🎯 {titulo}\n"
        f"{empresa}\n"
        f"📍 {pais}\n"
        f"💰 {prefix}{symbol} {value}/mês\n\n"
        f"✓ {requisito}\n\n"
        f"APLICAR: {link}"
    )


def main():
    load_env()
    global _BRAVE_QUOTA_EXCEEDED
    global _BRAVE_REQUESTS
    _BRAVE_QUOTA_EXCEEDED = False
    _BRAVE_REQUESTS = 0
    print(f"Brave token: {'OK' if _brave_token() else 'MISSING'}")
    # speed up resolver
    try:
        import link_resolver
        link_resolver.REQUEST_DELAY = 0.5
        link_resolver.REQUEST_TIMEOUT = 10
    except Exception:
        pass
    print("== FASE 1: COLETA ==")
    jobs = []
    count_before = 0
    jobs += fetch_companies_from_db(COMPANIES_JOBS_LIMIT)
    companies_count = len(jobs) - count_before
    count_before = len(jobs)
    jobs += fetch_brave_direct(150)
    brave_direct_count = len(jobs) - count_before
    jobs += fetch_remotive(60)
    jobs += fetch_remoteok(60)
    jobs += fetch_himalayas(60)
    jobs += fetch_jobicy(60)
    jobs += fetch_workingnomads(60)
    jobs += fetch_landingjobs(60)
    jobs += fetch_weworkremotely(60)
    print(f"Coletadas: {len(jobs)}")
    print(f"  - companies-db: {companies_count}")
    print(f"  - brave-direct: {brave_direct_count}")
    by_source = {}
    for j in jobs:
        by_source[j.get("source")] = by_source.get(j.get("source"), 0) + 1
    print(f"Por fonte: {by_source}")

    print("== FASE 2: FILTRO GEO ==")
    geo = []
    for j in jobs:
        if not is_allowed_geo(str(j.get("location", "")), str(j.get("description", ""))):
            continue
        geo.append(j)
    print(f"Após geo: {len(geo)}")

    print("== FASE 2B: FILTRO 48H (quando disponível) ==")
    recent = []
    for j in geo:
        if is_recent(j.get("posted_at"), hours=MAX_AGE_HOURS):
            recent.append(j)
    print(f"Após {MAX_AGE_HOURS}h: {len(recent)}")

    # prioriza brave
    recent.sort(key=lambda x: 0 if x.get("source") == "brave" else 1)

    print("== FASE 3: LINK DIRETO OFICIAL ==")
    seen_urls = load_history(HISTORY_URLS)
    seen_companies = load_history(HISTORY_COMPANIES)
    candidates = []
    companies_run = set()
    ats_count = 0
    max_ats_ratio = float(os.environ.get("ATS_MAX_RATIO", "0.4") or "0.4")
    max_ats_count = int(os.environ.get("ATS_MAX_COUNT", "6") or "6")
    min_allow = int(os.environ.get("ATS_MIN_ALLOW", "5") or "5")
    attempts = 0
    fallback_calls = 0
    resolver_calls = 0
    start_time = time.time()
    for j in recent:
        attempts += 1
        if attempts > 120:
            break
        if time.time() - start_time > 120:
            break
        src = j.get("source_url") or ""
        if not src:
            continue
        if j.get("source") == "weworkremotely":
            direct_url = ""
        elif j.get("source") == "brave" and is_valid_direct_url(src):
            direct_url = src
        elif is_valid_direct_url(src):
            direct_url = src
        else:
            direct_url = ""
            if resolver_calls < 15:
                resolved, _status = resolve_direct_url(src)
                resolver_calls += 1
                if resolved and is_valid_direct_url(resolved):
                    direct_url = resolved
            # evita resolver agregadores pesados; usa fallback com Brave
            if not direct_url:
                if fallback_calls < 40:
                    direct_url = fallback_search_direct(j)
                    fallback_calls += 1
                else:
                    direct_url = ""
            if not direct_url:
                continue
            if not is_valid_direct_url(direct_url):
                continue
        # tenta inferir empresa pelo ATS antes das validações
        if direct_url:
            inferred_company = infer_company_from_direct_url(direct_url) or infer_company_from_url(direct_url)
            if inferred_company:
                j["company"] = clean_company_name(inferred_company)

        if not direct_url:
            # tenta encontrar link oficial no domínio da empresa
            fallback = search_company_job_link(j.get("company") or "", j.get("title") or "")
            if not fallback:
                continue
            final_url = fallback
            if not (is_company_job_url(final_url, j.get("company") or "") or is_allowed_company_listing(final_url, j.get("company") or "")):
                continue
            j["direct_url"] = final_url
            # segue para dedupe/enriquecimento
        else:
            if not is_job_specific_url(direct_url):
                continue
        # evita listagens
        if direct_url:
            if "greenhouse.io" in direct_url and "/jobs/" not in direct_url:
                continue
        if j.get("company"):
            j["company"] = clean_company_name(j.get("company"))
        company_name = j.get("company") or ""
        if direct_url:
            # se link final ainda é ATS, tenta achar link oficial no domínio da empresa
            final_url = direct_url
            if not (is_company_job_url(final_url, company_name) or is_allowed_company_listing(final_url, company_name)):
                # permite ATS se nome da empresa estiver na URL
                if is_allowed_ats_url(final_url, company_name):
                    j["direct_url"] = final_url
                else:
                    resolved_company = resolve_official_company_link(final_url)
                    if not resolved_company:
                        # fallback por nome da empresa + título (útil para WWR e agregadores)
                        if time.time() - start_time > 110:
                            resolved_company = ""
                        else:
                            resolved_company = search_company_job_link(company_name, j.get("title") or "")
                    if not resolved_company:
                        continue
                    final_url = resolved_company
                    if not (is_company_job_url(final_url, company_name) or is_allowed_company_listing(final_url, company_name)):
                        continue
                    j["direct_url"] = final_url
        if not j.get("company") or j.get("company") == "Unknown":
            continue
        if is_generic_title(j.get("title")):
            continue
        # enriquecer
        if "greenhouse.io" in direct_url:
            enrich_greenhouse(j)
        elif "lever.co" in direct_url:
            enrich_lever(j)
        if looks_like_listing(j.get("description", "")):
            continue
        if not j.get("company") or j.get("company") == "Unknown":
            continue
        # dedupe histórico
        company_key = (j.get("company") or "").strip().lower()
        if company_key in seen_companies:
            continue
        if company_key in companies_run:
            continue
        if direct_url in seen_urls:
            continue
        if direct_url and is_ats_url(direct_url):
            if len(candidates) >= min_allow:
                projected = (ats_count + 1) / max(1, len(candidates) + 1)
                if ats_count >= max_ats_count or projected > max_ats_ratio:
                    continue
        companies_run.add(company_key)
        candidates.append(j)
        if direct_url and is_ats_url(direct_url):
            ats_count += 1
        if len(candidates) >= 50:
            break
    print(f"Com link direto: {len(candidates)}")

    if not candidates:
        print("Sem candidatos suficientes")
        return

    print("== FASE 4: LLM (Gemini) ==")
    merged = []
    batch_size = 5
    usage = load_llm_usage()
    if LLM_DAILY_LIMIT <= 0:
        print("LLM desativado (LLM_DAILY_LIMIT=0)")
    for start in range(0, len(candidates), batch_size):
        if LLM_DAILY_LIMIT <= 0:
            break
        if usage["count"] >= LLM_DAILY_LIMIT:
            print("Limite diário de LLM atingido; parando análise.")
            break
        chunk = candidates[start:start + batch_size]
        payload = build_llm_payload(chunk)
        try:
            results = call_gemini(payload, len(chunk))
        except Exception as e:
            print(f"Erro LLM (chunk {start}): {e}")
            continue
        usage["count"] += 1
        save_llm_usage(usage)
        for i, res in enumerate(results):
            if i >= len(chunk):
                break
            job = chunk[i].copy()
            # força empresa a partir do dado real
            if isinstance(res, dict):
                res["job_index"] = len(merged)
                res["empresa"] = job.get("company") or res.get("empresa")
                if not res.get("titulo"):
                    res["titulo"] = job.get("title")
                if not res.get("pais") or "worldwide" in str(res.get("pais")).lower():
                    inferred = infer_country_from_location(normalize_location(job.get("location")))
                    if inferred:
                        res["pais"] = inferred
            job["analysis"] = res
            merged.append(job)

    print("== FASE 5: DIVERSIDADE ==")
    analyses = [m["analysis"] for m in merged]
    approved = []
    for a in analyses:
        if a.get("aprovada") is False:
            continue
        if a.get("internacional_ok") is False:
            continue
        if not llm_country_allowed(a.get("pais")):
            continue
        approved.append(a)
    print(f"Aprovadas (LLM): {len(approved)} / {len(analyses)}")
    target_size = int(os.environ.get("BATCH_SIZE", "20"))
    batch = select_diverse_batch(approved, size=target_size)
    if not batch:
        print("Nenhum lote passou diversidade — usando fallback")
        batch = pick_with_requirements(approved, target_size)

    # montar lote final com dados originais
    final = []
    for item in batch:
        idx = item.get("job_index")
        if idx is None:
            continue
        if idx < len(merged):
            job = merged[idx]
            final.append(job)

    # remove itens sem link e ordena para evitar links semelhantes em sequência
    final = [j for j in final if j.get("direct_url")]
    final = interleave_by_domain(final)

    # salvar para revisão
    out = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(final),
        "items": final,
    }
    out_path = DATA_DIR / "batch_ready.json"
    with open(out_path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # salvar versão pronta para Telegram
    posts_path = Path(os.environ.get("TELEGRAM_POSTS_PATH") or (DATA_DIR / "telegram_posts.txt"))
    with open(posts_path, "w") as f:
        for j in final:
            f.write(format_post(j))
            f.write("\n\n---\n\n")

    print("== RESULTADO ==")
    print(f"Prontas para revisão: {len(final)}")
    print(f"Posts prontos em: {posts_path}")


if __name__ == "__main__":
    main()
