# 🚀 VAGAS REMOTAS - SCALING PLAN

## Status: ⏸️ MODO TESTE (igual ao FREE)

**Aguardando comando:** "vamos começar"

---

## 📊 Configuração Atual (TESTE)

| Canal | Vagas/dia | Crons | Status |
|-------|-----------|-------|--------|
| PAGO | 5 | 5x/dia | ✅ Ativo |
| FREE | 5 | 5x/dia | ✅ Ativo |

---

## 🎯 Configuração Final (APÓS "vamos começar")

| Canal | Vagas/dia | Crons | Mudanças |
|-------|-----------|-------|----------|
| PAGO | 30 | 30x/dia (~34min) | Aumentar crons |
| FREE | 3 | 3x/dia | Reduzir + pular vagas |

### Mudanças necessárias:

#### 1. PAGO: Aumentar para 30/dia
```bash
# Substituir crons atuais por 30 entradas
# Ver PAID_SETUP.md para lista completa de horários
```

#### 2. FREE: Reduzir para 3/dia + pular vagas
```bash
# Modificar post_next.py para incrementar index em 10 (não 1)
# Ou criar post_next_free.py com lógica de skip
```

#### 3. Coleta: Aumentar para ~250/semana
```bash
# Modificar weekly_collect.sh
# Adicionar mais fontes
# Aumentar limites de scraping
```

---

## 🔧 Comandos para Ativar

Quando Mestre disser "vamos começar":

```bash
# 1. Ativar crons PAGO (30/dia)
cd /home/ubuntu/projects/job-curator-bot
cat cron_pago_30.txt >> /tmp/newcron.txt
crontab /tmp/newcron.txt

# 2. Modificar FREE para pular vagas
# (script já preparado em post_next_free_skip.py)
mv post_next.py post_next_backup.py
mv post_next_free_skip.py post_next.py

# 3. Aumentar coleta
# (configuração em weekly_collect_expanded.sh)
```

---

## 📁 Arquivos Preparados

| Arquivo | Função | Status |
|---------|--------|--------|
| `cron_pago_30.txt` | Crons para 30 vagas/dia | ⏳ Criar |
| `post_next_free_skip.py` | FREE com skip 1/10 | ⏳ Criar |
| `weekly_collect_expanded.sh` | Coleta 250/semana | ⏳ Criar |

---

## ⚠️ NÃO ESQUECER

1. Este arquivo existe para lembrar do plano
2. Quando Mestre disser "vamos começar", executar as mudanças
3. Testar antes de ativar em produção

---

**Criado:** 2026-02-06
**Última atualização:** 2026-02-06
**Responsável:** Akira
