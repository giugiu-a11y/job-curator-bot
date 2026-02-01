#!/bin/bash
# Job Curator Bot - Script simplificado
# Descobre → Filtra → Posta

export PYTHONPATH=/home/ubuntu/projects/job-curator-bot:$PYTHONPATH
cd /home/ubuntu/projects/job-curator-bot

# Load env
export $(grep -v '^#' .env | xargs)

# 1. Descobre vagas
echo "🔍 Descobrindo vagas..."
python3 << 'PYSCRIPT'
import feedparser
import json
from datetime import datetime

jobs = []

# WWR
print("  → We Work Remotely...")
try:
    feed = feedparser.parse('https://weworkremotely.com/categories/2-remote-design-jobs/feed')
    for entry in feed.entries[:10]:
        jobs.append({
            'id': entry.get('id', entry.get('link', '')),
            'title': entry.get('title', 'N/A'),
            'company': entry.get('author', 'Unknown'),
            'link': entry.get('link', ''),
            'description': entry.get('summary', '')[:500],
            'source': 'weworkremotely'
        })
except: pass

# Himalayas
print("  → Himalayas...")
try:
    feed = feedparser.parse('https://himalayas.app/rss')
    for entry in feed.entries[:10]:
        jobs.append({
            'id': entry.get('id', entry.get('link', '')),
            'title': entry.get('title', 'N/A'),
            'company': entry.get('author', 'Unknown'),
            'link': entry.get('link', ''),
            'description': entry.get('summary', '')[:500],
            'source': 'himalayas'
        })
except: pass

# Salva
with open('/tmp/jobs_discovered.json', 'w') as f:
    json.dump(jobs, f)

print(f"✅ Descobertas: {len(jobs)} vagas")
PYSCRIPT

# 2. Filtra (rejeita óbvios)
echo "🔍 Filtrando..."
python3 << 'PYSCRIPT'
import json

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

with open('/tmp/jobs_filtered.json', 'w') as f:
    json.dump(filtered[:5], f)  # Top 5 pro FREE
PYSCRIPT

# 3. Posta
echo "📲 Postando no Telegram..."
python3 << 'PYSCRIPT'
import json
import os
import requests

with open('/tmp/jobs_filtered.json') as f:
    jobs = json.load(f)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN_FREE')
CHANNEL = os.environ.get('TELEGRAM_CHANNEL_FREE')

for i, job in enumerate(jobs, 1):
    msg = f"""
🌍 VAGA #{i}

📌 {job['title']}
🏢 {job['company']}

📝 {job['description'][:100]}...

🔗 {job['link']}
"""
    
    try:
        requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            json={'chat_id': CHANNEL, 'text': msg.strip()}
        )
        print(f"✅ Vaga {i} postada")
    except Exception as e:
        print(f"❌ Erro: {e}")

PYSCRIPT

echo "✅ CICLO COMPLETO"
