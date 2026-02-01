#!/usr/bin/env bash
set -euo pipefail

# carrega env global (se existir e legível)
if [ -r /etc/llm.env ]; then
  set -a
  . /etc/llm.env || true
  set +a
fi

LOCK="/tmp/job_curator.lock"
SCRIPT="$1"; shift || true

ENV="/home/ubuntu/projects/job-curator-bot/.env"
if [ -f "$ENV" ]; then
  set -a
  . "$ENV"
  set +a
fi

exec flock -w 3600 "$LOCK" timeout 20m "$SCRIPT" "$@"
