# VAGAS_REMOTAS_CHECKLIST - Daily Principles

**Projeto:** Vagas Remotas  
**Objetivo:** Entregar vagas reais, seguras, de site oficial da empresa

---

## ✅ CHECKLIST DIÁRIO

### ENTRADA (Descoberta)
- [ ] Scrapers rodando (RemoteOK, WWR, Himalayas, LinkedIn, etc)
- [ ] Vagas sendo coletadas de múltiplas fontes
- [ ] ⚠️ **Não importa de onde vem — importa a saída**

### PROCESSAMENTO (Pré-filtro)
- [ ] Rejeitar "US Only", "North America Only", "No Visa"
- [ ] Rejeitar MLM, comissão pura, suspeitas
- [ ] Validar categoria (Tech, Marketing, Design, Ops, Sales, Healthcare, Education, AI/ML)
- [ ] ⚠️ **Gemini NÃO chamado ainda — economizar tokens**

### LINK RESOLVER (Crítico)
- [ ] Se URL é agregador (Indeed, LinkedIn, Glassdoor, RemoteOK, WWR):
  - [ ] Acessar página do agregador
  - [ ] Extrair link direto (Greenhouse, Lever, Workday, Ashby, /careers/)
  - [ ] Validar que funciona (status < 400)
- [ ] Se URL já é direto:
  - [ ] Validar que ainda funciona (não 404)
- [ ] ❌ **NUNCA postar link de agregador**
- [ ] ✅ **SEMPRE postar link direto verificado**

### ANÁLISE (Gemini - depois de resolver link)
- [ ] Salário: Inferir se não informado
  - [ ] 75% das vagas: > USD $4.000/mês
  - [ ] 25% das vagas: < USD $4.000/mês (mas cumprindo outros requisitos)
- [ ] Geografia: Aceita internacional?
- [ ] Área: Diversificar (não só Tech)
- [ ] Qualidade: Profissional, não golpe?

### FILA (Regra 75/25)
- [ ] FREE: 5 vagas/dia
  - [ ] 3-4 vagas > $4k
  - [ ] 1-2 vagas < $4k
- [ ] PAGO: 30 vagas/dia
  - [ ] ~22-23 vagas > $4k
  - [ ] ~7-8 vagas < $4k

### ENTREGA (Telegram)
- [ ] Cada vaga postada com:
  - [ ] Título
  - [ ] Empresa
  - [ ] Emoji (área)
  - [ ] Salário (se tiver)
  - [ ] ✅ **Link DIRETO, VERIFICADO, FUNCIONA**
- [ ] Link sempre é:
  - [ ] ✅ boards.greenhouse.io/empresa/vaga
  - [ ] ✅ jobs.lever.co/empresa/vaga
  - [ ] ✅ empresa.wd5.myworkdaysite.com/...
  - [ ] ✅ empresa.com/careers/vaga-especifica
  - [ ] ❌ Nunca: indeed.com, linkedin.com, remoteok.com, weworkremotely.com

### HISTÓRIA (Reutilização)
- [ ] Vagas não usadas hoje → Salvar com data
- [ ] Amanhã: Re-testar link (ainda funciona?)
- [ ] Se tá vivo → Reutilizar, se 404 → Descartar

---

## 📊 MÉTRICAS DIÁRIAS

| Métrica | Target | Frequência |
|---------|--------|-----------|
| Vagas descobertas | 50+ | Diário |
| % com link direto | 85%+ | Diário |
| % com salário inf. | 70%+ | Diário |
| FREE postadas | 5 | Diário |
| PAGO postadas | 30 | Diário |
| Erro de link | <5% | Diário |

---

## 🚫 NUNCA FAZER

1. ❌ Postar link de agregador (Indeed, LinkedIn, etc)
2. ❌ Postar vaga sem verificar link (pode tá 404)
3. ❌ Aceitar "US Only" ou "No Visa" (rejeitar)
4. ❌ Gastar Gemini em vagas obviamente ruins
5. ❌ Desbalancear ratio 75/25 (greed de vagas baratas)

---

## ✅ SEMPRE FAZER

1. ✅ Resolver agregador → link direto (Link Resolver)
2. ✅ Validar link (HEAD request, status < 400)
3. ✅ Diversificar áreas (não só Tech)
4. ✅ Manter 75/25 (qualidade)
5. ✅ Reutilizar vagas antigas (se link tá vivo)
6. ✅ Economizar tokens (pré-filtro antes de Gemini)

---

**Última atualização:** 2026-01-29  
**Mantido por:** Akira (Vagas Remotas Engineer)
