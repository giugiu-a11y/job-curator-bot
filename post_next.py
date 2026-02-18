#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import requests
import subprocess
import time
import urllib.parse
import urllib.request


DATA_DIR = Path(__file__).parent / "data"
QUEUE_PATH = DATA_DIR / "post_queue.json"
POSTS_PATH = DATA_DIR / "telegram_posts.txt"
FAIL_STATE_PATH = DATA_DIR / "post_failures.json"
PAUSE_FLAG_PATH = DATA_DIR / "posting_paused.json"


def load_env():
    for path in (
        "/etc/llm.env",
        "/home/ubuntu/.config/clawdbot/gateway.env",
        "/home/ubuntu/.config/openclaw/gateway.env",
        str(Path(__file__).parent / ".env"),
    ):
        try:
            if not os.path.exists(path) or not os.access(path, os.R_OK):
                continue
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    v = v.strip()
                    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                        v = v[1:-1]
                    os.environ[k] = v
        except (FileNotFoundError, PermissionError, OSError):
            # Skip unreadable or restricted locations.
            continue


def load_queue():
    if not QUEUE_PATH.exists():
        return {"index": 0}
    with open(QUEUE_PATH) as f:
        return json.load(f)


def save_queue(data):
    with open(QUEUE_PATH, "w") as f:
        json.dump(data, f)


def load_posts():
    if not POSTS_PATH.exists():
        return []
    text = POSTS_PATH.read_text()
    parts = [p.strip() for p in text.split("\n\n---\n\n") if p.strip()]
    return parts


def save_posts(posts):
    text = "\n\n---\n\n".join(posts) + "\n"
    POSTS_PATH.write_text(text)


def extract_domain(post_text: str):
    for line in post_text.splitlines():
        line = line.strip()
        if line.lower().startswith("aplicar:"):
            url = line.split(":", 1)[1].strip()
            try:
                host = urllib.parse.urlparse(url).hostname or ""
            except Exception:
                host = ""
            return host.lower()
    # fallback: first URL anywhere
    for token in post_text.split():
        if token.startswith("http://") or token.startswith("https://"):
            try:
                host = urllib.parse.urlparse(token).hostname or ""
            except Exception:
                host = ""
            return host.lower()
    return ""


def _send_via_requests(url: str, payload: dict):
    last_err = None
    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, timeout=15)
            if not r.ok:
                raise RuntimeError(f"Telegram error {r.status_code}: {r.text[:200]}")
            return
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"requests_failed: {last_err}")


def _send_via_urllib(url: str, payload: dict):
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()


def _send_via_curl(url: str, payload: dict):
    # Fallback for environments where python HTTPS is blocked.
    data = urllib.parse.urlencode(payload)
    cmd = ["curl", "-sS", "-X", "POST", "-d", data, url]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"curl_failed: {res.stderr.strip()[:200]}")


def send_telegram(text: str):
    token = os.environ.get("TELEGRAM_TOKEN_FREE") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHANNEL_FREE") or os.environ.get("TELEGRAM_GROUP_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_TOKEN_FREE/TELEGRAM_CHANNEL_FREE não configurados")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    try:
        _send_via_requests(url, payload)
        return
    except Exception:
        pass
    try:
        _send_via_urllib(url, payload)
        return
    except Exception:
        pass
    _send_via_curl(url, payload)


def get_alert_config():
    token = os.environ.get("TELEGRAM_ALERT_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_ALERT_CHAT_ID")
    if token and chat_id:
        return token, chat_id
    return None, None


def send_alert(message: str):
    token, chat_id = get_alert_config()
    if not token or not chat_id:
        print("ALERTA: TELEGRAM_ALERT_* não configurado")
        return
    # Safety: never send alerts to group/channel ids (start with -100)
    if str(chat_id).startswith("-100"):
        print("ALERTA: chat_id aponta para grupo/canal; ignorado")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": f"⚠️ ALERTA VAGAS REMOTAS: {message}", "disable_web_page_preview": True}
    try:
        _send_via_requests(url, payload)
        return
    except Exception as e:
        last_err = e
    try:
        _send_via_urllib(url, payload)
        return
    except Exception as e:
        last_err = e
    try:
        _send_via_curl(url, payload)
        return
    except Exception as e:
        last_err = e
    print(f"ALERTA: falha ao enviar alerta: {last_err}")


def load_fail_state():
    if not FAIL_STATE_PATH.exists():
        return {"count": 0}
    try:
        with open(FAIL_STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {"count": 0}


def save_fail_state(state):
    with open(FAIL_STATE_PATH, "w") as f:
        json.dump(state, f)


def pause_posting(reason: str):
    already_paused = PAUSE_FLAG_PATH.exists()
    if not already_paused:
        PAUSE_FLAG_PATH.write_text(json.dumps({"paused": True, "reason": reason}) + "\n")
        send_alert(f"Postagens pausadas (2 falhas seguidas). Motivo: {reason}")
    print("Postagens pausadas.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--alert-test", action="store_true")
    args = parser.parse_args()
    load_env()
    if args.alert_test:
        send_alert("Teste de alerta (job-curator-bot).")
        print("OK: alerta enviado")
        return
    if PAUSE_FLAG_PATH.exists():
        print("Postagens pausadas (flag ativa).")
        return

    posts = load_posts()
    if not posts:
        print("Sem posts disponíveis.")
        send_alert("Sem posts disponíveis para publicar.")
        return
    queue = load_queue()
    idx = int(queue.get("index", 0))
    if idx >= len(posts):
        print("Fila concluída.")
        return
    # Evita links com o mesmo domínio em sequência (melhorado)
    prev_domain = extract_domain(posts[idx - 1]) if idx > 0 else ""
    curr_domain = extract_domain(posts[idx])
    
    # Também evita mesmo domínio base (ex: jobs.lever.co → lever.co)
    def base_domain(d):
        parts = d.split('.')
        if len(parts) >= 2:
            return '.'.join(parts[-2:])
        return d
    
    prev_base = base_domain(prev_domain)
    curr_base = base_domain(curr_domain)
    
    if prev_base and curr_base and prev_base == curr_base:
        swap_idx = None
        for j in range(idx + 1, len(posts)):
            next_domain = extract_domain(posts[j])
            next_base = base_domain(next_domain)
            if next_base and next_base != prev_base:
                swap_idx = j
                break
        if swap_idx is not None:
            posts[idx], posts[swap_idx] = posts[swap_idx], posts[idx]
            save_posts(posts)
    try:
        send_telegram(posts[idx])
    except Exception as e:
        print(f"Erro ao postar: {e}")
        state = load_fail_state()
        state["count"] = int(state.get("count", 0)) + 1
        save_fail_state(state)
        if state["count"] >= 2:
            pause_posting(str(e))
        else:
            send_alert(f"Falha ao postar vaga {idx+1}: {e}")
        return
    # sucesso: zera contador de falhas
    save_fail_state({"count": 0})
    queue["index"] = idx + 1
    save_queue(queue)
    print(f"OK: post {idx+1}/{len(posts)} enviado")


if __name__ == "__main__":
    main()
