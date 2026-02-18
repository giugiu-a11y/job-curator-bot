#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="/home/ubuntu/projects/job-curator-bot/logs"
MAX_BYTES="${LOG_ROTATE_MAX_BYTES:-2097152}"
KEEP="${LOG_ROTATE_KEEP:-3}"

if [ ! -d "$LOG_DIR" ]; then
  exit 0
fi

rotate_file() {
  local file="$1"
  local size
  size=$(stat -c%s "$file" 2>/dev/null || echo 0)
  if [ "$size" -lt "$MAX_BYTES" ]; then
    return 0
  fi
  local i
  for ((i=KEEP; i>=1; i--)); do
    if [ -f "${file}.${i}" ]; then
      if [ "$i" -eq "$KEEP" ]; then
        rm -f "${file}.${i}"
      else
        mv "${file}.${i}" "${file}.$((i+1))"
      fi
    fi
  done
  mv "$file" "${file}.1"
  : > "$file"
}

for f in "$LOG_DIR"/*.log; do
  [ -f "$f" ] || continue
  rotate_file "$f"
done
