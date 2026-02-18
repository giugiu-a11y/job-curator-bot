#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path

import requests

from prepare_daily_batch import (
    load_env,
    is_job_specific_url,
    llm_country_allowed,
    is_company_domain_url,
    host_has_company_label,
)
from link_resolver import is_valid_direct_url


DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def call_gemini_seed(count: int = 10):
    api_key = os.environ.get("GOOGLE_API_KEY") or ""
    model = os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash-lite"
    if not api_key:
        raise ValueError("GOOGLE_API_KEY não configurada")

    prompt = f"""
Gere uma lista JSON com {count} vagas REAIS abertas nas últimas 48 horas.
Países permitidos: EUA, Canadá, Europa, Austrália.
Cada item deve conter:
- titulo (em português)
- empresa
- pais
- url_oficial (link direto da vaga no site oficial/ATS da empresa)

Regras:
- Não incluir Brasil, LATAM, Índia, Filipinas, etc.
- Evite vagas com cidadania obrigatória.
- Se não tiver certeza do link oficial, use null no url_oficial.
- Preferir URLs diretas de ATS (Greenhouse/Lever/Workday/Ashby/etc) ou página oficial da vaga.
- O campo url_oficial deve ter no máximo 200 caracteres.

Retorne SOMENTE JSON array.
""".strip()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048,
            "response_mime_type": "application/json",
        },
    }

    def _parse_json(text_out: str):
        text_out = text_out.strip()
        if text_out.startswith("```"):
            text_out = text_out.strip("`")
            text_out = text_out.replace("json", "", 1).strip()
        try:
            return json.loads(text_out)
        except Exception:
            start = text_out.find("[")
            end = text_out.rfind("]")
            chunk = text_out
            if start != -1 and end != -1 and end > start:
                chunk = text_out[start : end + 1]
            try:
                return json.loads(chunk)
            except Exception:
                import ast
                return ast.literal_eval(chunk)

    for attempt in range(3):
        r = requests.post(url, json=body, timeout=60)
        if not r.ok:
            if r.status_code in (429, 503):
                time.sleep(5 + attempt * 5)
                continue
            raise ValueError(f"Gemini HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        cand = (data.get("candidates") or [{}])[0]
        parts = ((cand.get("content") or {}).get("parts") or [])
        text_out = parts[0].get("text") if parts else ""
        if not text_out:
            raise ValueError("Gemini resposta vazia")
        try:
            result = _parse_json(text_out)
        except Exception:
            # tenta mais uma vez com instrução reforçada
            if attempt < 2:
                body["contents"][0]["parts"][0]["text"] = (
                    prompt + "\n\nRetorne SOMENTE JSON válido sem texto extra."
                )
                time.sleep(2)
                continue
            raise
        if not isinstance(result, list):
            raise ValueError(f"Gemini result is not a list: {type(result)}")
        return result

    raise ValueError("Gemini request failed")


def url_is_live(url: str) -> bool:
    if not url:
        return False
    try:
        r = requests.head(url, timeout=15, allow_redirects=True)
        if r.status_code < 400:
            return True
    except Exception:
        pass
    try:
        r = requests.get(url, timeout=20, allow_redirects=True, stream=True)
        return r.status_code < 400
    except Exception:
        return False


def looks_like_search_or_listing(url: str) -> bool:
    u = (url or "").lower()
    if "search=" in u or "keyword=" in u or "query=" in u:
        return True
    if u.endswith("/jobs") or u.endswith("/jobs/"):
        return True
    if "/jobs/?" in u or "/job/?" in u:
        return True
    return False


def main():
    load_env()
    print("== LLM SEED ==")
    seeds = []
    rounds = int(os.environ.get("LLM_SEED_ROUNDS", "3"))
    per_round = int(os.environ.get("LLM_SEED_BATCH_SIZE", "10"))
    for _ in range(rounds):
        try:
            seeds.extend(call_gemini_seed(per_round))
        except Exception as e:
            print(f"Erro Gemini: {e}")
            continue
    print(f"Geradas: {len(seeds)}")

    validated = []
    seen_companies = set()
    for item in seeds:
        if not isinstance(item, dict):
            continue
        title = (item.get("titulo") or "").strip()
        company = (item.get("empresa") or "").strip()
        country = (item.get("pais") or "").strip()
        url = (item.get("url_oficial") or "").strip()

        if not title or not company or not country:
            continue
        if not llm_country_allowed(country):
            continue
        key = company.lower()
        if key in seen_companies:
            continue

        ok = False
        reason = ""
        if url and len(url) > 300:
            url = ""
        if not url:
            reason = "sem_url"
        elif not is_valid_direct_url(url):
            reason = "url_nao_direta"
        elif not (is_company_domain_url(url) or host_has_company_label(company, url)):
            reason = "url_nao_empresa"
        elif not is_job_specific_url(url):
            reason = "url_nao_especifica"
        elif looks_like_search_or_listing(url):
            reason = "url_listagem"
        elif not url_is_live(url):
            reason = "url_inativa"
        else:
            ok = True

        if ok:
            seen_companies.add(key)
            validated.append({
                "titulo": title,
                "empresa": company,
                "pais": country,
                "url_oficial": url,
            })
        else:
            validated.append({
                "titulo": title,
                "empresa": company,
                "pais": country,
                "url_oficial": url,
                "rejeitada": reason,
            })

    out = {
        "generated_at": time.time(),
        "count": len(validated),
        "items": validated,
    }
    out_path = DATA_DIR / "llm_seed_candidates.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    ok_count = len([i for i in validated if "rejeitada" not in i])
    print(f"Válidas: {ok_count} / {len(validated)}")
    print(f"Arquivo: {out_path}")


if __name__ == "__main__":
    main()
