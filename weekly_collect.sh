#!/bin/bash
set -euo pipefail

export PYTHONPATH=/home/ubuntu/projects/job-curator-bot:$PYTHONPATH
cd /home/ubuntu/projects/job-curator-bot

# Load env
if [ -r /etc/llm.env ]; then
  set -a
  . /etc/llm.env || true
  set +a
fi

export BRAVE_BUDGET="${BRAVE_BUDGET:-60}"
export BRAVE_QUERY_LIMIT="${BRAVE_QUERY_LIMIT:-40}"
export BATCH_SIZE="${BATCH_SIZE:-30}"
export TELEGRAM_POSTS_PATH="/home/ubuntu/projects/job-curator-bot/data/telegram_posts_new.txt"

python3 /home/ubuntu/projects/job-curator-bot/prepare_daily_batch.py

# Append new batch to pool (append-only) + append posts to master
python3 - <<'PY'
import json
from pathlib import Path

base = Path('/home/ubuntu/projects/job-curator-bot/data')
ready = base / 'batch_ready.json'
pool = base / 'batch_pool.json'
posts_new = base / 'telegram_posts_new.txt'
posts_master = base / 'telegram_posts.txt'

def load_json(p):
    if not p.exists():
        return {}
    with open(p) as f:
        return json.load(f)

data = load_json(ready)
items = data.get('items', [])

pool_data = load_json(pool) or {"items": []}
existing = {i.get('direct_url') for i in pool_data.get('items', []) if i.get('direct_url')}
added = 0
for it in items:
    url = it.get('direct_url')
    if not url or url in existing:
        continue
    pool_data['items'].append(it)
    existing.add(url)
    added += 1

with open(pool, 'w') as f:
    json.dump(pool_data, f, ensure_ascii=False, indent=2)

# append posts (avoid duplicates by link)
if posts_new.exists():
    master_links = set()
    if posts_master.exists():
        text = posts_master.read_text()
        for block in text.split('\\n\\n---\\n\\n'):
            for line in block.splitlines():
                if line.startswith('APLICAR:'):
                    master_links.add(line.replace('APLICAR:','').strip())
    new_blocks = posts_new.read_text().split('\\n\\n---\\n\\n')
    append_blocks = []
    for block in new_blocks:
        if not block.strip():
            continue
        link = ''
        for line in block.splitlines():
            if line.startswith('APLICAR:'):
                link = line.replace('APLICAR:','').strip()
                break
        if link and link not in master_links:
            append_blocks.append(block.strip())
            master_links.add(link)
    if append_blocks:
        mode = 'a' if posts_master.exists() else 'w'
        with open(posts_master, mode) as f:
            if mode == 'a':
                f.write('\\n\\n---\\n\\n')
            f.write('\\n\\n---\\n\\n'.join(append_blocks))

print('pool added', added, 'total', len(pool_data.get('items', [])))
PY

# init queue pointer if missing
python3 - <<'PY'
import json
from pathlib import Path
q = Path('/home/ubuntu/projects/job-curator-bot/data/post_queue.json')
if not q.exists():
    q.parent.mkdir(parents=True, exist_ok=True)
    with open(q, 'w') as f:
        json.dump({"index": 0}, f)
    print("queue initialized")
PY
