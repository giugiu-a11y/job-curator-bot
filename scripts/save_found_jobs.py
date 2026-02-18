#!/usr/bin/env python3
import json
import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BATCH_READY = DATA_DIR / "batch_ready.json"
OUT_PATH = Path(os.environ.get("FOUND_JOBS_PATH") or (DATA_DIR / "jobs_found.json"))


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def main():
    batch = load_json(BATCH_READY, {})
    items = batch.get("items") or []
    if not items:
        print("Nenhuma vaga em batch_ready.json")
        return

    existing = load_json(OUT_PATH, [])
    seen = set()
    for j in existing:
        url = j.get("direct_url") or j.get("source_url") or ""
        if url:
            seen.add(url)

    added = 0
    for j in items:
        url = j.get("direct_url") or j.get("source_url") or ""
        if not url or url in seen:
            continue
        existing.append(j)
        seen.add(url)
        added += 1

    OUT_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n")
    print(f"Salvas: {added}. Total: {len(existing)}")


if __name__ == "__main__":
    main()
