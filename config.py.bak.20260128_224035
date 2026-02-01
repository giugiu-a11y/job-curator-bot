"""
Job Curator Bot - Configurações Centralizadas
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega .env PRIMEIRO
load_dotenv(Path(__file__).parent / '.env')

# =============================================================================
# PATHS
# =============================================================================
BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get('DATA_DIR', BASE_DIR / 'data'))
DATABASE_PATH = DATA_DIR / 'jobs.db'

# =============================================================================
# API KEYS (do .env)
# =============================================================================
TELEGRAM_TOKEN_FREE = os.environ.get('TELEGRAM_TOKEN_FREE')
TELEGRAM_TOKEN_PAID = os.environ.get('TELEGRAM_TOKEN_PAID')
TELEGRAM_CHANNEL_FREE = os.environ.get('TELEGRAM_CHANNEL_FREE', '@VagasRemotasFree')
TELEGRAM_CHANNEL_PAID = os.environ.get('TELEGRAM_CHANNEL_PAID', '@VagasRemotasPremium')
CLAUDE_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

# =============================================================================
# LIMITES DE VAGAS
# =============================================================================
JOBS_PER_DAY_FREE = 5       # Vagas no canal gratuito (3-5 conforme spec)
JOBS_PER_DAY_PAID = 30      # Vagas no canal pago (ATUALIZADO: era 20, agora 30)

# =============================================================================
# MIX DE SALÁRIO (Regra 75/25)
# =============================================================================
SALARY_HIGH_THRESHOLD = 4000    # USD/mês - considerado "alto"
SALARY_HIGH_PERCENTAGE = 0.75   # 75% das vagas devem ser > $4k
SALARY_LOW_PERCENTAGE = 0.25    # 25% podem ser < $4k (mas cumprindo outros requisitos)

# =============================================================================
# HORÁRIOS DE EXECUÇÃO
# =============================================================================
SCHEDULE_HOURS = ['03:00', '09:00', '15:00']  # 3x ao dia, começando de madrugada

# =============================================================================
# FILTROS GEOGRÁFICOS
# =============================================================================
# Países/regiões ACEITOS
ACCEPTED_REGIONS = [
    'worldwide', 'global', 'remote', 'anywhere',
    'usa', 'us', 'united states', 'america',
    'canada', 'ca',
    'europe', 'eu', 'uk', 'united kingdom', 'germany', 'netherlands', 
    'france', 'spain', 'portugal', 'ireland', 'sweden', 'denmark',
    'asia', 'singapore', 'japan', 'australia', 'new zealand',
    'latam', 'latin america', 'brazil', 'brasil',
]

# Termos que REJEITAM a vaga (restrição geográfica)
REJECTION_TERMS = [
    'us only', 'usa only', 'us residents only', 'us citizens only',
    'must be located in us', 'must reside in us',
    'north america only', 'na only',
    'uk only', 'eu only', 'europe only',
    'must be authorized to work in',
    'visa sponsorship is not available',
    'no visa sponsorship',
    'work permit required',
    'must have right to work',
]

# =============================================================================
# CATEGORIAS DE VAGAS (para diversidade)
# =============================================================================
JOB_CATEGORIES = [
    'Technology',       # Dev, DevOps, Data, etc
    'Marketing',        # Marketing, Growth, SEO, Content
    'Design',           # UI/UX, Product Design, Graphic
    'Operations',       # Ops, Admin, HR, Finance
    'Sales',            # Sales, Business Dev, Account
    'Healthcare',       # Health, Medical, Biotech
    'Education',        # Teaching, Training, EdTech
    'AI/ML',            # AI, Machine Learning, Data Science
    'Other',            # Outros
]

# =============================================================================
# LINKS VÁLIDOS (diretos das empresas)
# =============================================================================
VALID_JOB_DOMAINS = [
    'greenhouse.io',
    'lever.co',
    'myworkdaysite.com',
    'workday.com',
    'ashbyhq.com',
    'bamboohr.com',
    'recruitee.com',
    'breezy.hr',
    'smartrecruiters.com',
    'jobvite.com',
    'icims.com',
    'ultipro.com',
    'paylocity.com',
    'jazz.co',
    'applytojob.com',
    'workable.com',
]

# Domínios genéricos que devemos RESOLVER para o link real
AGGREGATOR_DOMAINS = [
    'indeed.com',
    'linkedin.com',
    'glassdoor.com',
    'ziprecruiter.com',
    'monster.com',
    'remoteok.com',
    'weworkremotely.com',
    'himalayas.app',
]

# =============================================================================
# SCRAPING
# =============================================================================
REQUEST_TIMEOUT = 30  # segundos
REQUEST_DELAY = 5     # segundos entre requests (rate limiting - devagar)
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# =============================================================================
# GEMINI
# =============================================================================
GEMINI_MODEL = 'gemini-2.0-flash'
GEMINI_DELAY = 10  # segundos entre chamadas (rate limiting - devagar para não estourar)
