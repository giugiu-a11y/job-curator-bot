#!/bin/bash
# =============================================================================
# VAGAS REMOTAS - Post no Canal PAGO
# =============================================================================
# Uso: ./post_paid.sh
# Chamado via cron múltiplas vezes ao dia (30 vagas/dia)

set -e
cd "$(dirname "$0")"

# Lock para evitar execução paralela
LOCKFILE="/tmp/job_curator_paid.lock"
exec 200>"$LOCKFILE"
flock -n 200 || { echo "Já rodando (lock ativo)"; exit 0; }

# Executa
python3 post_next_paid.py

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Post PAGO concluído"
