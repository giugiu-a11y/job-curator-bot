#!/bin/bash
# Versão simplificada - usa scrapers testados
cd /home/ubuntu/projects/job-curator-bot

export $(cat .env | grep -v '^#' | xargs)

python3 << 'PYSCRIPT'
import sys
sys.path.insert(0, '/home/ubuntu/projects/job-curator-bot')

from scrapers.weworkremotely import WeWorkRemotelyScraper
from scrapers.himalayas import HimalayasScraper
import json
import os
import requests
from datetime import datetime

print("🔍 Descobrindo vagas...")

# Scrape WWR
jobs = []
try:
    wwr = WeWorkRemotelyScraper()
    wwr_jobs = wwr.run(limit=3)
    jobs.extend(wwr_jobs)
    print(f"  ✅ WWR: {len(wwr_jobs)}")
except Exception as e:
    print(f"  ❌ WWR: {str(e)[:50]}")

# Scrape Himalayas
try:
    hima = HimalayasScraper()
    hima_jobs = hima.run(limit=3)
    jobs.extend(hima_jobs)
    print(f"  ✅ Himalayas: {len(hima_jobs)}")
except Exception as e:
    print(f"  ❌ Himalayas: {str(e)[:50]}")

print(f"\n✅ Total: {len(jobs)} vagas descobertas\n")

if not jobs:
    print("❌ Nenhuma vaga encontrada")
    sys.exit(0)

# Post to Telegram
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN_FREE')
CHANNEL = os.environ.get('TELEGRAM_CHANNEL_FREE')

print("📲 Postando no Telegram...\n")

for i, job in enumerate(jobs[:5], 1):
    title = job.get('title', 'N/A')[:40]
    company = job.get('company', 'Unknown')
    link = job.get('source_url', job.get('link', '#'))
    
    msg = f"""
🌍 VAGA REMOTA #{i}

📌 {title}
🏢 {company}

🔗 {link}
"""
    
    try:
        r = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            json={'chat_id': CHANNEL, 'text': msg.strip()},
            timeout=10
        )
        if r.status_code == 200:
            print(f"✅ Vaga {i} postada")
        else:
            print(f"⚠️ Vaga {i}: {r.text[:50]}")
    except Exception as e:
        print(f"❌ Vaga {i}: {str(e)[:50]}")

print("\n✅ CICLO COMPLETO")
PYSCRIPT
