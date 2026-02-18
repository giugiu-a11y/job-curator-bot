# Ambiente e chaves

## Onde as variáveis são lidas
Ordem de carregamento no `prepare_daily_batch.py`:
1. `/etc/llm.env`
2. `/home/ubuntu/.config/clawdbot/gateway.env`
3. `./.env` (na raiz do projeto)

O `config.py` também carrega `./.env` diretamente.

## Chaves essenciais
- `TELEGRAM_TOKEN_FREE`
- `TELEGRAM_TOKEN_PAID`
- `TELEGRAM_CHANNEL_FREE`
- `TELEGRAM_CHANNEL_PAID`
- `GOOGLE_API_KEY`
- `BRAVE_API_KEY` (ou `BRAVE_SEARCH_API_KEY`)

## Diagnóstico rápido
Execute:
```bash
python3 scripts/check_env.py
```
