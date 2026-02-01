#!/bin/bash
# Post vaga #5 às 21:00 BRT

cd /home/ubuntu/projects/job-curator-bot

python3 -c "
import json, os, requests

TOKEN = 'None'
GROUP_ID = -1003378765936

with open('/tmp/jobs_validated.json') as f:
    jobs = json.load(f)

if 4 < len(jobs):
    j = jobs[4]
    msg = f'VAGA REMOTA\n\n{j.get("title", "N/A")}\n{j.get("company", "Unknown")}\n\nAPLICAR: {j.get("source_url", "#")}'
    requests.post(f'https://api.telegram.org/bot{TOKEN}/sendMessage', json={'chat_id': GROUP_ID, 'text': msg})
    print(f'✅ Vaga 5 postada')
"
