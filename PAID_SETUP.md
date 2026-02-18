# 💎 VAGAS REMOTAS - CANAL PAGO (PREMIUM)

## Status: ⏳ Aguardando Configuração

---

## 📋 Checklist de Setup

### 1. Credenciais Telegram (VOCÊ precisa fazer)

- [ ] **Criar bot no BotFather** → copiar token
- [ ] **Criar grupo/canal PAGO** no Telegram
- [ ] **Adicionar bot como admin** do grupo
- [ ] **Pegar ID do grupo** (usar @userinfobot ou similar)

### 2. Configurar .env.paid

```bash
cd /home/ubuntu/projects/job-curator-bot
cp .env.paid.example .env.paid
nano .env.paid  # Preencher com tokens reais
chmod 600 .env.paid
```

### 3. Testar Postagem

```bash
cd /home/ubuntu/projects/job-curator-bot
python3 post_next_paid.py --test  # Mostra vaga sem postar
python3 post_next_paid.py         # Posta de verdade
```

### 4. Configurar Cron (30 vagas/dia)

```bash
crontab -e
```

Adicionar (30 posts entre 06:00 e 23:00 BRT = 09:00-02:00 UTC):

```cron
# VAGAS REMOTAS PAGO - 30 vagas/dia (~1 a cada 34min)
# Bloco 1: 09:00-14:00 UTC (06:00-11:00 BRT) - 9 vagas
0 9 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
34 9 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
8 10 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
42 10 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
16 11 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
50 11 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
24 12 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
58 12 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
32 13 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1

# Bloco 2: 14:00-19:00 UTC (11:00-16:00 BRT) - 9 vagas
6 14 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
40 14 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
14 15 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
48 15 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
22 16 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
56 16 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
30 17 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
4 18 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
38 18 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1

# Bloco 3: 19:00-02:00 UTC (16:00-23:00 BRT) - 12 vagas
12 19 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
46 19 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
20 20 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
54 20 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
28 21 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
2 22 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
36 22 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
10 23 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
44 23 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
18 0 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
52 0 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
26 1 * * * cd /home/ubuntu/projects/job-curator-bot && ./post_paid.sh >> logs/paid.log 2>&1
```

---

## 💳 Sistema de Pagamento (Fase 2)

### Opção A: Telegram Payments + Stripe

1. Criar conta Stripe (stripe.com)
2. Configurar Telegram Payments no BotFather
3. Bot processa pagamento e libera acesso

### Opção B: Hotmart/Kiwify Webhook

1. Configurar webhook na plataforma
2. Endpoint recebe notificação de compra
3. Bot adiciona usuário ao grupo

### Opção C: Manual (MVP)

1. Usuário paga (Pix, etc)
2. Admin verifica e adiciona manualmente
3. Escala mal, mas funciona para começar

---

## 🔐 Segurança do Grupo

| Controle | Status |
|----------|--------|
| Grupo privado | ⏳ Você criar |
| Bot como admin | ⏳ Você configurar |
| Verificação de pagamento | ⏳ Fase 2 |
| Remoção automática | ⏳ Fase 2 |

---

## 📁 Arquivos Criados

| Arquivo | Função |
|---------|--------|
| `post_next_paid.py` | Script de postagem PAGO |
| `post_paid.sh` | Wrapper para cron |
| `.env.paid.example` | Template de configuração |
| `PAID_SETUP.md` | Este documento |

---

## 🚀 Próximos Passos

1. **VOCÊ:** Envia tokens do BotFather (bot + grupo PAGO)
2. **EU:** Configuro .env.paid e testo
3. **EU:** Ativo crons
4. **VOCÊ:** Decide método de pagamento
5. **EU:** Implemento controle de acesso

---

**Criado:** 2026-02-06
**Mantido por:** Akira
