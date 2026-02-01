#!/usr/bin/env python3
"""
Post a single job to Telegram by index.
Usage: python3 post_job.py <index>

Requires environment variables:
  TELEGRAM_BOT_TOKEN - Bot token from @BotFather
  TELEGRAM_GROUP_ID  - Chat ID (negative for groups)
  JOBS_FILE          - (optional) Path to jobs JSON, default /tmp/jobs_validated.json
"""
import json
import os
import sys

import requests


def get_required_env(name: str) -> str:
    """Get required env var or exit with clear error."""
    # Source .env if not in environ
    if name not in os.environ:
        try:
            with open('.env') as f:
                for line in f:
                    if '=' in line and not line.startswith('#'):
                        key, val = line.split('=', 1)
                        os.environ[key.strip()] = val.strip()
        except FileNotFoundError:
            pass
    
    val = os.environ.get(name, "").strip()
    if not val or val.lower() in ("none", "cole_aqui_o_token_real"):
        sys.exit(f"ERRO: {name} não definido ou inválido. Configure no .env")
    return val


def main():
    if len(sys.argv) < 2:
        sys.exit("Uso: python3 post_job.py <index>")

    idx = int(sys.argv[1])

    # Load env vars with validation
    token = get_required_env("TELEGRAM_BOT_TOKEN")
    group_id = get_required_env("TELEGRAM_GROUP_ID")
    jobs_file = os.environ.get("JOBS_FILE", "/tmp/jobs_validated.json")

    # Load jobs
    try:
        with open(jobs_file, "r", encoding="utf-8") as f:
            jobs = json.load(f)
    except FileNotFoundError:
        sys.exit(f"ERRO: Arquivo não encontrado: {jobs_file}")
    except json.JSONDecodeError as e:
        sys.exit(f"ERRO: JSON inválido em {jobs_file}: {e}")

    if idx >= len(jobs):
        print(f"SKIP: idx {idx} >= {len(jobs)} vagas disponíveis")
        sys.exit(0)

    j = jobs[idx]
    title = j.get("title", "N/A")
    company = j.get("company", "Unknown")
    url = j.get("source_url", "")

    msg = f"VAGA REMOTA\n\n{title}\n{company}\n\nAPLICAR: {url}"

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": int(group_id),
            "text": msg,
            "disable_web_page_preview": True,
        },
        timeout=15,
    )

    if not resp.ok:
        print(f"ERRO Telegram: {resp.status_code} - {resp.text}")
        sys.exit(1)

    print(f"OK: Vaga {idx} postada ({title[:40]}...)")


if __name__ == "__main__":
    main()
