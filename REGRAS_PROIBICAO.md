# 🚫 REGRAS DE PROIBIÇÃO - Vagas Remotas

**Consolidado em:** 2026-02-06
**Fonte:** Mestre (MT)

---

## 1. Proibições de Link

### NUNCA postar link de agregador:
- ❌ indeed.com
- ❌ linkedin.com
- ❌ glassdoor.com
- ❌ remoteok.com (como destino final)
- ❌ weworkremotely.com (como destino final)
- ❌ himalayas.app (como destino final)
- ❌ remotive.com (como destino final)
- ❌ workingnomads.com (como destino final)
- ❌ jobicy.com (como destino final)
- ❌ landing.jobs (como destino final)

### SEMPRE resolver para link direto:
- ✅ boards.greenhouse.io/empresa/jobs/ID
- ✅ jobs.lever.co/empresa/ID
- ✅ empresa.wd5.myworkdaysite.com/...
- ✅ jobs.ashbyhq.com/empresa/ID
- ✅ empresa.com/careers/vaga-especifica

### Validação obrigatória:
- ❌ Greenhouse sem `/jobs/` no caminho
- ❌ Lever sem `/jobs/` no caminho
- ❌ Link com status HTTP >= 400
- ❌ Link que não foi validado

---

## 2. Proibições de Conteúdo

### Restrição geográfica (REJEITAR):
```
us only, usa only, us residents only, us citizens only
must be located in us, must reside in us
north america only, na only
uk only, eu only, europe only
must be authorized to work in
visa sponsorship is not available, no visa sponsorship
work permit required, must have right to work
```

### Esquemas suspeitos (REJEITAR):
- ❌ MLM / marketing multinível
- ❌ Comissão pura sem salário base
- ❌ "Seja seu próprio chefe"
- ❌ Esquemas de pirâmide

### Vagas genéricas (REJEITAR):
- ❌ Sem empresa identificável
- ❌ "Pool" de candidatos (sem vaga específica)

### Páginas de listagem (REJEITAR):
Detectar via `looks_like_listing()`:
```
current openings, create a job alert, sent directly to your inbox
view all jobs, jobs at, open positions
```

---

## 3. Proibições Operacionais

- ❌ NUNCA gastar IA (Gemini/LLM) em vagas obviamente ruins
- ❌ NUNCA desbalancear o mix 75/25 (salário)
- ❌ NUNCA postar sem pré-filtro

---

## 4. Implementação

### Função `quick_reject()`:
```python
REJECT_TERMS = [
    'us only', 'usa only', 'us residents only', 'us citizens only',
    'must be located in us', 'must reside in us',
    'north america only', 'na only',
    'uk only', 'eu only', 'europe only',
    'must be authorized to work in',
    'visa sponsorship is not available', 'no visa sponsorship',
    'work permit required', 'must have right to work',
    'mlm', 'commission only', 'be your own boss',
]
```

### Função `looks_like_listing()`:
```python
def looks_like_listing(text: str) -> bool:
    t = (text or '').lower()
    return any(x in t for x in [
        'current openings', 'create a job alert', 
        'sent directly to your inbox',
        'view all jobs', 'jobs at', 'open positions'
    ])
```

### Validação de link direto:
```python
def is_valid_job_link(url: str) -> bool:
    if 'greenhouse.io' in url and '/jobs/' not in url:
        return False
    if 'lever.co' in url and '/jobs/' not in url:
        return False
    # Verificar status HTTP < 400
    try:
        r = requests.head(url, timeout=10, allow_redirects=True)
        return r.status_code < 400
    except:
        return False
```

---

## 5. Fluxo Correto

```
COLETA (agregadores) 
    ↓
PRÉ-FILTRO (quick_reject) 
    ↓
RESOLUÇÃO (agregador → link direto)
    ↓
VALIDAÇÃO (status HTTP, /jobs/, not listing)
    ↓
ENRIQUECIMENTO (API Greenhouse/Lever)
    ↓
POSTAGEM (só vagas válidas)
```

---

**Mantido por:** Akira
