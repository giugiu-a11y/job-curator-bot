#!/bin/bash
set -euo pipefail

# test_batch_analysis.sh - Teste completo do bot Vagas Remotas
# Executa: scrapers → pré-filtro → batch Claude → posting

cd "$(dirname "$0")"
source .env

LOG="/tmp/vagas_remotas_test.log"
APPROVED_JSON="vagas_aprovadas_test.json"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"
}

log "=== TESTE VAGAS REMOTAS ==="

# 1. Descoberta (scrapers - TEMP: usar arquivo mock)
log "FASE 1: Descoberta..."
python3 -c "
import json
from scrapers import get_all_scrapers

scrapers = get_all_scrapers()
all_jobs = []
for scraper in scrapers:
    try:
        jobs = scraper.run(limit=10)
        all_jobs.extend(jobs)
        print(f'{scraper.name}: {len(jobs)} vagas')
    except Exception as e:
        print(f'{scraper.name}: ERRO - {e}')

print(f'Total: {len(all_jobs)} vagas descobertas')
with open('_temp_raw_jobs.json', 'w') as f:
    json.dump(all_jobs[:5], f)  # Só 5 pro teste
" 2>&1 | tee -a "$LOG" || log "⚠️ Scrapers com erro (usar mock)"

# 2. Pré-filtro (regex, zero IA)
log "FASE 2: Pré-filtro..."
python3 -c "
import json
from job_analyzer import quick_reject_check

with open('_temp_raw_jobs.json') as f:
    jobs = json.load(f)

filtered = []
for job in jobs:
    reason = quick_reject_check(job)
    if not reason:
        filtered.append(job)
        print(f'✅ {job.get(\"title\", \"N/A\")[:40]}')
    else:
        print(f'❌ {job.get(\"title\", \"N/A\")[:40]} - {reason[:40]}')

print(f'Resultado: {len(filtered)} aprovadas no pré-filtro')
with open('_temp_filtered_jobs.json', 'w') as f:
    json.dump(filtered, f)
" 2>&1 | tee -a "$LOG"

# 3. Batch Claude (1 call = 5 vagas)
log "FASE 3: Análise Claude (Batch)..."
python3 -c "
import json
from job_analyzer import batch_analyze_jobs_single_call

with open('_temp_filtered_jobs.json') as f:
    jobs = json.load(f)

results = batch_analyze_jobs_single_call(jobs)
print(f'Análise concluída: {len(results)} vagas processadas')

approved = [r for r in results if r.get('aprovada')]
print(f'Aprovadas: {len(approved)}')

with open('$APPROVED_JSON', 'w') as f:
    json.dump(approved, f, ensure_ascii=False, indent=2)
" 2>&1 | tee -a "$LOG"

# 4. Posting (Telegram)
log "FASE 4: Posting no Telegram..."
python3 post_job.py 0 2>&1 | tee -a "$LOG" || log "⚠️ Post falhou"
python3 post_job.py 1 2>&1 | tee -a "$LOG" || log "⚠️ Post falhou"
python3 post_job.py 2 2>&1 | tee -a "$LOG" || log "⚠️ Post falhou"
python3 post_job.py 3 2>&1 | tee -a "$LOG" || log "⚠️ Post falhou"
python3 post_job.py 4 2>&1 | tee -a "$LOG" || log "⚠️ Post falhou"

# 5. Summary
log "=== TESTE CONCLUÍDO ==="
log "Log: $LOG"
log "Aprovadas: $(grep -c 'true' "$APPROVED_JSON" || echo 0)"

# Cleanup
rm -f _temp_raw_jobs.json _temp_filtered_jobs.json

log "✅ Teste finalizado"
