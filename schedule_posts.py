#!/usr/bin/env python3
"""
Agenda 5 vagas em 5 horários diferentes (1 por dia)
Horários: 09:00, 12:00, 15:00, 18:00, 21:00 BRT
"""
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')

# IDs
TOKEN = os.environ.get('TELEGRAM_TOKEN_FREE')
GROUP_ID = -1003378765936

SCHEDULE_TIMES = [
    "0 9 * * *",    # 09:00
    "0 12 * * *",   # 12:00
    "0 15 * * *",   # 15:00
    "0 18 * * *",   # 18:00
    "0 21 * * *",   # 21:00
]

CRON_JOB_TEMPLATE = f"""#!/bin/bash
export TELEGRAM_TOKEN_FREE="{TOKEN}"
export GROUP_ID="{GROUP_ID}"

cd /home/ubuntu/projects/job-curator-bot

python3 << 'PYSCRIPT'
import os, json, requests
from pathlib import Path

# Ler vagas salvas
with open('/tmp/jobs_validated.json') as f:
    jobs = json.load(f)

# Pega vaga do índice (0-4)
idx = $INDEX
if idx < len(jobs):
    job = jobs[idx]
    
    # Formata
    msg = f"""🌍 VAGA REMOTA

📌 {{job.get('title', 'N/A')}}
🏢 {{job.get('company', 'Unknown')}}

💰 {{job.get('salary_inferred', '~USD 3-5k')}}/mês
📊 {{job.get('level_casual', 'Qualquer nível')}}

📝 {{job.get('description', '')[:150]}}

🔗 APLICAR AQUI
{{job.get('source_url', '')}}"""
    
    # Post
    requests.post(
        f'https://api.telegram.org/bot$TOKEN/sendMessage',
        json={{'chat_id': {GROUP_ID}, 'text': msg}},
        timeout=10
    )
    print(f"✅ Vaga {{idx+1}} postada")
else:
    print("❌ Índice inválido")

PYSCRIPT
"""

# Salvar cron jobs
for i, cron_expr in enumerate(SCHEDULE_TIMES):
    script_content = CRON_JOB_TEMPLATE.replace("$INDEX", str(i))
    script_path = f"/home/ubuntu/projects/job-curator-bot/post_job_{i}.sh"
    
    with open(script_path, 'w') as f:
        f.write(script_content)
    
    os.chmod(script_path, 0o755)
    print(f"✅ Script {i+1} criado: {script_path}")

print("\n📋 Próximo passo: adicionar ao crontab")
print("crontab -e e adicionar:")
for i, cron_expr in enumerate(SCHEDULE_TIMES):
    print(f"{cron_expr} /home/ubuntu/projects/job-curator-bot/post_job_{i}.sh")
