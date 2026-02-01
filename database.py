"""
Job Curator Bot - Database (SQLite)
Gerencia vagas, fila, histórico e reaproveitamento
"""
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import contextmanager
import logging

from config import DATABASE_PATH, DATA_DIR

logger = logging.getLogger(__name__)


def init_database():
    """Inicializa o banco de dados com as tabelas necessárias"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Tabela de vagas descobertas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company TEXT,
                category TEXT,
                salary_min INTEGER,
                salary_max INTEGER,
                salary_currency TEXT DEFAULT 'USD',
                description TEXT,
                source_url TEXT,
                direct_url TEXT,
                location TEXT,
                is_remote BOOLEAN DEFAULT 1,
                accepts_international BOOLEAN,
                raw_data TEXT,
                discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                analyzed_at TIMESTAMP,
                analysis_result TEXT,
                status TEXT DEFAULT 'pending'
            )
        ''')
        
        # Tabela de vagas postadas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posted_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                channel_type TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                message_id TEXT,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        ''')
        
        # Tabela de fila de vagas aprovadas (para posting)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS job_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL UNIQUE,
                priority INTEGER DEFAULT 0,
                is_high_salary BOOLEAN DEFAULT 0,
                queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        ''')
        
        # Índices para performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_category ON jobs(category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_queue_priority ON job_queue(priority DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_posted_channel ON posted_jobs(channel_type, channel_id)')
        
        conn.commit()
        logger.info(f"Database inicializado: {DATABASE_PATH}")


@contextmanager
def get_connection():
    """Context manager para conexão com o banco"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# =============================================================================
# JOBS CRUD
# =============================================================================

def job_exists(job_id: str) -> bool:
    """Verifica se uma vaga já existe no banco"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM jobs WHERE id = ?', (job_id,))
        return cursor.fetchone() is not None


def save_job(job: dict) -> bool:
    """Salva uma vaga no banco"""
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO jobs 
                (id, title, company, category, salary_min, salary_max, salary_currency,
                 description, source_url, direct_url, location, is_remote, 
                 accepts_international, raw_data, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                job['id'],
                job.get('title'),
                job.get('company'),
                job.get('category'),
                job.get('salary_min'),
                job.get('salary_max'),
                job.get('salary_currency', 'USD'),
                job.get('description'),
                job.get('source_url'),
                job.get('direct_url'),
                job.get('location'),
                job.get('is_remote', True),
                job.get('accepts_international'),
                json.dumps(job.get('raw_data', {})),
                'pending'
            ))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Erro ao salvar job {job.get('id')}: {e}")
            return False


def update_job_analysis(job_id: str, analysis: dict, status: str):
    """Atualiza a análise de uma vaga"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE jobs 
            SET analyzed_at = ?, analysis_result = ?, status = ?,
                category = COALESCE(?, category),
                accepts_international = COALESCE(?, accepts_international)
            WHERE id = ?
        ''', (
            datetime.now().isoformat(),
            json.dumps(analysis),
            status,
            analysis.get('category'),
            analysis.get('accepts_international'),
            job_id
        ))
        conn.commit()


def update_job_direct_url(job_id: str, direct_url: str):
    """Atualiza o link direto de uma vaga"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE jobs SET direct_url = ? WHERE id = ?
        ''', (direct_url, job_id))
        conn.commit()


def get_pending_jobs(limit: int = 50) -> list:
    """Retorna vagas pendentes de análise"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM jobs 
            WHERE status = 'pending' 
            ORDER BY discovered_at ASC 
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_approved_jobs_without_direct_url(limit: int = 50) -> list:
    """Retorna vagas aprovadas que ainda não têm link direto"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM jobs 
            WHERE status = 'approved' AND (direct_url IS NULL OR direct_url = '')
            ORDER BY discovered_at ASC 
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# QUEUE MANAGEMENT
# =============================================================================

def add_to_queue(job_id: str, is_high_salary: bool, expires_hours: int = 72):
    """Adiciona vaga à fila de posting"""
    with get_connection() as conn:
        cursor = conn.cursor()
        expires_at = datetime.now() + timedelta(hours=expires_hours)
        priority = 10 if is_high_salary else 5
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO job_queue 
                (job_id, priority, is_high_salary, expires_at)
                VALUES (?, ?, ?, ?)
            ''', (job_id, priority, is_high_salary, expires_at.isoformat()))
            conn.commit()
        except Exception as e:
            logger.error(f"Erro ao adicionar à fila: {e}")


def get_jobs_for_posting(channel_type: str, limit: int, 
                         high_salary_ratio: float = 0.75) -> list:
    """
    Retorna vagas para posting respeitando:
    - Limite diário
    - Proporção 75% high salary / 25% outros
    - Não repetir vagas já postadas neste canal
    """
    high_salary_limit = int(limit * high_salary_ratio)
    low_salary_limit = limit - high_salary_limit
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Vagas high salary (> $4k)
        cursor.execute('''
            SELECT j.*, q.is_high_salary FROM job_queue q
            JOIN jobs j ON q.job_id = j.id
            WHERE q.is_high_salary = 1
            AND q.expires_at > datetime('now')
            AND j.direct_url IS NOT NULL AND j.direct_url != ''
            AND q.job_id NOT IN (
                SELECT job_id FROM posted_jobs 
                WHERE channel_type = ?
            )
            ORDER BY q.priority DESC, q.queued_at ASC
            LIMIT ?
        ''', (channel_type, high_salary_limit))
        high_salary_jobs = [dict(row) for row in cursor.fetchall()]
        
        # Vagas low salary (resto)
        cursor.execute('''
            SELECT j.*, q.is_high_salary FROM job_queue q
            JOIN jobs j ON q.job_id = j.id
            WHERE q.is_high_salary = 0
            AND q.expires_at > datetime('now')
            AND j.direct_url IS NOT NULL AND j.direct_url != ''
            AND q.job_id NOT IN (
                SELECT job_id FROM posted_jobs 
                WHERE channel_type = ?
            )
            ORDER BY q.priority DESC, q.queued_at ASC
            LIMIT ?
        ''', (channel_type, low_salary_limit))
        low_salary_jobs = [dict(row) for row in cursor.fetchall()]
        
        # Combina mantendo proporção
        all_jobs = high_salary_jobs + low_salary_jobs
        return all_jobs


def mark_as_posted(job_id: str, channel_type: str, channel_id: str, message_id: str = None):
    """Marca vaga como postada"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO posted_jobs (job_id, channel_type, channel_id, message_id)
            VALUES (?, ?, ?, ?)
        ''', (job_id, channel_type, channel_id, message_id))
        conn.commit()


def remove_from_queue(job_id: str):
    """Remove vaga da fila"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM job_queue WHERE job_id = ?', (job_id,))
        conn.commit()


def cleanup_expired_queue():
    """Remove vagas expiradas da fila"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM job_queue WHERE expires_at < datetime('now')
        ''')
        deleted = cursor.rowcount
        conn.commit()
        if deleted > 0:
            logger.info(f"Removidas {deleted} vagas expiradas da fila")


def get_queue_stats() -> dict:
    """Retorna estatísticas da fila"""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM job_queue WHERE expires_at > datetime("now")')
        total = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM job_queue WHERE is_high_salary = 1 AND expires_at > datetime("now")')
        high_salary = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM jobs WHERE status = "pending"')
        pending = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM jobs WHERE status = "approved"')
        approved = cursor.fetchone()[0]
        
        return {
            'queue_total': total,
            'queue_high_salary': high_salary,
            'queue_low_salary': total - high_salary,
            'jobs_pending': pending,
            'jobs_approved': approved
        }


def verify_and_requeue_unused_jobs(link_verifier_func=None):
    """
    Verifica vagas que não foram postadas hoje mas estão na fila.
    Se o link ainda estiver ativo, reutiliza a vaga.
    Se o link estiver morto (404), remove da fila.
    
    Args:
        link_verifier_func: Função que verifica se um link está ativo
                           (pode ser verify_url_is_active do link_resolver)
    
    Returns:
        dict: {reused: int, removed_dead_links: int}
    """
    from datetime import timedelta
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Busca vagas na fila que NÃO foram postadas hoje
        yesterday = (datetime.now() - timedelta(days=1)).date()
        
        cursor.execute('''
            SELECT DISTINCT q.job_id, j.direct_url, j.title
            FROM job_queue q
            JOIN jobs j ON q.job_id = j.id
            WHERE NOT EXISTS (
                SELECT 1 FROM posted_jobs p 
                WHERE p.job_id = q.job_id 
                AND DATE(p.posted_at) = DATE('now')
            )
            AND q.expires_at > datetime('now')
            ORDER BY q.priority DESC
        ''')
        
        unused = cursor.fetchall()
        reused = 0
        removed = 0
        
        for job in unused:
            job_id = job[0]
            direct_url = job[1]
            title = job[2]
            
            # Se temos verificador de link, verifica se ainda está ativo
            if link_verifier_func and direct_url:
                is_active = link_verifier_func(direct_url)
                if not is_active:
                    # Link morto - remove da fila
                    logger.warning(f"Link morto - removendo vaga: {title[:40]}")
                    remove_from_queue(job_id)
                    removed += 1
                    continue
            
            # Link está ok - requeue com nova data de expiração
            expires_at = datetime.now() + timedelta(hours=72)
            cursor.execute('''
                UPDATE job_queue 
                SET queued_at = datetime('now'), expires_at = ?
                WHERE job_id = ?
            ''', (expires_at.isoformat(), job_id))
            
            reused += 1
            logger.info(f"Reutilizando vaga: {title[:40]}")
        
        conn.commit()
        
        return {'reused': reused, 'removed_dead_links': removed}


# Inicializa o banco ao importar
init_database()
