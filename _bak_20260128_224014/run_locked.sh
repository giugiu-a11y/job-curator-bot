#!/usr/bin/env bash
set -euo pipefail
LOCK="/tmp/job_curator.lock"
SCRIPT="$1"; shift || true

# 1h de espera máxima pra não empilhar infinito
# 20 min de teto por execução pra evitar runaway caro
exec flock -w 3600 "$LOCK" timeout 20m bash "$SCRIPT" "$@"
