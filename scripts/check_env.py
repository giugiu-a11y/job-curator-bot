#!/usr/bin/env python3
import os
from pathlib import Path


def load_env():
    for path in ("/etc/llm.env", "/home/ubuntu/.config/clawdbot/gateway.env", str(Path(__file__).resolve().parent.parent / ".env")):
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    v = v.strip()
                    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                        v = v[1:-1]
                    os.environ.setdefault(k, v)
        except FileNotFoundError:
            continue


def main():
    load_env()
    print(f"BRAVE: {'OK' if (os.environ.get('BRAVE_API_KEY') or os.environ.get('BRAVE_SEARCH_API_KEY') or os.environ.get('BRAVE_SUBSCRIPTION_TOKEN')) else 'MISSING'}")
    print(f"GOOGLE_API_KEY: {'OK' if os.environ.get('GOOGLE_API_KEY') else 'MISSING'}")
    print(f"ANTHROPIC_API_KEY: {'OK' if os.environ.get('ANTHROPIC_API_KEY') else 'MISSING'}")
    print(f"TELEGRAM_TOKEN_FREE: {'OK' if os.environ.get('TELEGRAM_TOKEN_FREE') else 'MISSING'}")
    print(f"TELEGRAM_TOKEN_PAID: {'OK' if os.environ.get('TELEGRAM_TOKEN_PAID') else 'MISSING'}")
    print(f"TELEGRAM_CHANNEL_FREE: {'OK' if os.environ.get('TELEGRAM_CHANNEL_FREE') else 'MISSING'}")
    print(f"TELEGRAM_CHANNEL_PAID: {'OK' if os.environ.get('TELEGRAM_CHANNEL_PAID') else 'MISSING'}")


if __name__ == "__main__":
    main()
