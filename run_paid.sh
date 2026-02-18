#!/bin/bash
# =============================================================================
# VAGAS REMOTAS PAGO - Script de Coleta e Postagem (modo teste)
# =============================================================================
set -e
export PYTHONPATH=/home/ubuntu/projects/job-curator-bot:$PYTHONPATH
cd /home/ubuntu/projects/job-curator-bot

# Load envs (ordem: sistema -> .env -> .env.paid)
if [ -r /etc/llm.env ]; then
  set -a && . /etc/llm.env || true && set +a
fi
set -a && source .env 2>/dev/null || true && set +a
set -a && source .env.paid 2>/dev/null || true && set +a

echo "🚀 VAGAS REMOTAS PAGO - $(date '+%Y-%m-%d %H:%M:%S')"

# =============================================================================
# 1. COLETA + FILTRO + LINK DIRETO (pipeline unificado)
# =============================================================================
echo ""
echo "🔍 [1/2] Gerando lote com Brave + fontes públicas..."

# BATCH_SIZE recomendado:
# - teste: 3 a 6
# - produção: 6 (30/dia ÷ 5 execuções)
export BATCH_SIZE="${BATCH_SIZE:-3}"
export TELEGRAM_POSTS_PATH="${TELEGRAM_POSTS_PATH:-/home/ubuntu/projects/job-curator-bot/data/telegram_posts.txt}"

python3 /home/ubuntu/projects/job-curator-bot/prepare_daily_batch.py
python3 /home/ubuntu/projects/job-curator-bot/scripts/save_found_jobs.py

# =============================================================================
# 2. POSTAGEM (modo teste por padrão)
# =============================================================================
echo ""
echo "📲 [2/2] Postagem PAGO..."

if [ "${TEST_MODE:-1}" = "1" ]; then
  echo "🧪 TEST MODE: não envia para o Telegram"
  python3 /home/ubuntu/projects/job-curator-bot/post_next_paid.py --test
else
  python3 /home/ubuntu/projects/job-curator-bot/post_next_paid.py
fi

echo ""
echo "🏁 CICLO PAGO COMPLETO - $(date '+%Y-%m-%d %H:%M:%S')"
