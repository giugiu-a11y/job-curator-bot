# 🎯 Job Curator Bot - M60/UDI

Bot curador de vagas de trabalho remoto para brasileiros que querem trabalhar para empresas internacionais.

## ✨ Diferenciais

- ✅ **Link direto da empresa** — Greenhouse, Lever, Workday (não agregadores)
- ✅ **Filtro inteligente** — Rejeita "US Only", aceita vagas globais
- ✅ **Mix de salário** — 75% acima de $4k/mês, 25% acessíveis
- ✅ **Diversidade** — Tech, Marketing, Design, Saúde, Humanas
- ✅ **Modelo Freemium** — Canal FREE (5/dia) + PAID (30/dia)
- ✅ **Reaproveitamento** — Vagas não usadas vão para o próximo dia

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                    JOB CURATOR BOT                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  DESCOBERTA      ANÁLISE         RESOLUÇÃO     POSTING  │
│  (Scrapers)      (Gemini)        (Links)       (TG)     │
│                                                          │
│  RemoteOK    →   Critérios   →   Link Real  →  FREE     │
│  WWR         →   M60/UDI     →   Direto     →  PAID     │
│  Himalayas   →               →                          │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## 📋 Critérios M60/UDI

### ✅ Aprovação
- Aceita candidatos internacionais (ou não menciona restrição)
- Empresas dos EUA, Canadá, Europa, Ásia, Oceania
- Salário > USD $4.000/mês (75% das vagas)
- Link direto da empresa (Greenhouse, Lever, etc)

### ❌ Rejeição
- "US Only", "North America Only", "Must be authorized to work in US"
- MLM, esquemas, comissão pura
- Links de agregadores (Indeed, LinkedIn, Glassdoor)
- Vagas genéricas sem empresa identificável

## 🚀 Instalação

### 1. Instalar Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
```

### 2. Configurar variáveis

```bash
cd /home/ubuntu/projects/job-curator-bot
cp .env.example .env
nano .env  # Preencha suas chaves
```

Inclua a chave do Brave para descoberta automática:
`BRAVE_API_KEY` (ou `BRAVE_SEARCH_API_KEY`).

### 3. Build e Run

```bash
docker-compose up -d --build
```

### 4. Ver logs

```bash
docker-compose logs -f
```

## ⏰ Horários de Execução

- **09:00** — Curadoria matinal
- **13:00** — Curadoria almoço
- **17:00** — Curadoria vespertina
- **21:00** — Curadoria noturna

(Horário de São Paulo)

## 📊 Limites

| Canal | Vagas/dia | Mix Salário |
|-------|-----------|-------------|
| FREE  | 5         | 75% >$4k    |
| PAID  | 30        | 75% >$4k    |

## 🔧 Comandos Úteis

```bash
# Ver status
docker-compose ps

# Ver logs em tempo real
docker-compose logs -f

# Reiniciar
docker-compose restart

# Parar
docker-compose down

# Rebuild (após mudanças no código)
docker-compose up -d --build
```

## 📁 Estrutura

```
job-curator-bot/
├── app.py                 # Orquestrador principal
├── config.py              # Configurações
├── database.py            # SQLite
├── job_analyzer.py        # Análise com Gemini
├── link_resolver.py       # Resolve links diretos
├── telegram_poster.py     # Posta nos canais
├── scrapers/
│   ├── base.py            # Classe base
│   ├── remoteok.py        # RemoteOK
│   ├── weworkremotely.py  # WWR
│   └── himalayas.py       # Himalayas
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── data/
    └── jobs.db            # Database SQLite
```

## 📝 Licença

Projeto privado - M60/UDI - Matheus Tomoto
