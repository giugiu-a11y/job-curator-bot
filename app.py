#!/usr/bin/env python3
"""
Job Curator Bot - Orquestrador Principal
Curador de Vagas de Trabalho Remoto para M60/UDI

Fluxo:
1. Scraping: Busca vagas em múltiplas fontes
2. Pré-filtro: Descarta vagas obviamente ruins (sem IA)
3. Análise: Gemini analisa com critérios M60
4. Link Resolver: Encontra link direto da empresa
5. Queue: Adiciona à fila respeitando proporção 75/25
6. Posting: Posta nos canais FREE e PAID
7. Cleanup: Remove vagas expiradas
"""
import asyncio
import logging
import time
import schedule
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Carrega .env
load_dotenv(Path(__file__).parent / '.env')

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('job-curator')

# Imports internos
from config import (
    SCHEDULE_HOURS,
    SALARY_HIGH_THRESHOLD,
    JOBS_PER_DAY_FREE,
    JOBS_PER_DAY_PAID,
    DATA_DIR,
    GEMINI_DELAY,
)
import database as db
from scrapers import get_all_scrapers
from job_analyzer import init_claude, analyze_job, quick_reject_check, batch_analyze_jobs
from link_resolver import resolve_direct_url, verify_url_is_active  # verify_url_is_active usado em run_posting()
from telegram_poster import (
    post_jobs_to_free_channel,
    post_jobs_to_paid_channel,
    format_daily_summary
)


async def run_discovery():
    """
    Fase 1: Descoberta de vagas
    Busca em todas as fontes configuradas
    """
    logger.info("=" * 60)
    logger.info("FASE 1: DESCOBERTA DE VAGAS")
    logger.info("=" * 60)
    
    all_jobs = []
    scrapers = get_all_scrapers()
    
    for scraper in scrapers:
        try:
            jobs = scraper.run(limit=30)
            all_jobs.extend(jobs)
            logger.info(f"  {scraper.name}: {len(jobs)} vagas")
        except Exception as e:
            logger.error(f"  {scraper.name}: ERRO - {e}")
    
    # Salva no banco (ignora duplicadas)
    new_count = 0
    for job in all_jobs:
        if not db.job_exists(job['id']):
            if db.save_job(job):
                new_count += 1
    
    logger.info(f"Total: {len(all_jobs)} vagas, {new_count} novas")
    return new_count


async def run_prefilter():
    """
    Fase 2: Pré-filtro (sem IA)
    Remove vagas obviamente ruins antes de gastar tokens
    """
    logger.info("=" * 60)
    logger.info("FASE 2: PRÉ-FILTRO")
    logger.info("=" * 60)
    
    pending = db.get_pending_jobs(limit=100)
    rejected = 0
    
    for job in pending:
        reason = quick_reject_check(job)
        if reason:
            db.update_job_analysis(job['id'], {'motivo_rejeicao': reason}, 'rejected')
            rejected += 1
    
    logger.info(f"Pré-filtradas: {rejected} vagas rejeitadas")
    return rejected


async def run_analysis():
    """
    Fase 3: Análise com Gemini
    Aplica critérios M60 completos
    """
    logger.info("=" * 60)
    logger.info("FASE 3: ANÁLISE (GEMINI)")
    logger.info("=" * 60)
    
    pending = db.get_pending_jobs(limit=15)  # Limite baixo para não estourar rate limit
    
    if not pending:
        logger.info("Nenhuma vaga pendente para analisar")
        return 0, 0
    
    client = init_claude()
    approved = 0
    rejected = 0
    
    for job in pending:
        try:
            result = analyze_job(job, client)
            
            if not result:
                logger.warning(f"  Falha na análise: {job.get('title', 'N/A')[:40]}")
                continue
            
            if result.get('aprovada'):
                is_high_salary = result.get('is_high_salary', False)
                db.update_job_analysis(job['id'], result, 'approved')
                db.add_to_queue(job['id'], is_high_salary)
                approved += 1
                logger.info(f"  ✅ {job.get('title', 'N/A')[:40]}")
            else:
                db.update_job_analysis(job['id'], result, 'rejected')
                rejected += 1
                logger.info(f"  ❌ {job.get('title', 'N/A')[:40]} - {result.get('motivo_rejeicao', 'N/A')[:30]}")
            
            time.sleep(GEMINI_DELAY)  # Rate limiting - devagar
            
        except Exception as e:
            logger.error(f"  Erro: {job.get('id')} - {e}")
    
    logger.info(f"Resultado: {approved} aprovadas, {rejected} rejeitadas")
    return approved, rejected


async def run_link_resolver():
    """
    Fase 4: Resolução de Links
    Encontra o link direto da empresa
    """
    logger.info("=" * 60)
    logger.info("FASE 4: LINK RESOLVER")
    logger.info("=" * 60)
    
    jobs = db.get_approved_jobs_without_direct_url(limit=20)
    
    if not jobs:
        logger.info("Nenhuma vaga precisando de link resolver")
        return 0, 0
    
    resolved = 0
    failed = 0
    
    for job in jobs:
        source_url = job.get('source_url')
        if not source_url:
            failed += 1
            continue
        
        direct_url, status = resolve_direct_url(source_url)
        
        if direct_url:
            db.update_job_direct_url(job['id'], direct_url)
            resolved += 1
            logger.info(f"  ✅ {job.get('title', 'N/A')[:40]}")
        else:
            # Remove da fila se não conseguir resolver o link
            db.remove_from_queue(job['id'])
            db.update_job_analysis(job['id'], {'link_error': status}, 'link_failed')
            failed += 1
            logger.warning(f"  ❌ {job.get('title', 'N/A')[:40]} - {status}")
        
        time.sleep(2)  # Rate limiting
    
    logger.info(f"Resultado: {resolved} resolvidos, {failed} falharam")
    return resolved, failed


async def run_posting():
    """
    Fase 5: Posting nos canais
    Respeita limites e proporção 75/25
    """
    logger.info("=" * 60)
    logger.info("FASE 5: POSTING")
    logger.info("=" * 60)
    
    # Limpa fila expirada
    db.cleanup_expired_queue()
    
    # Verifica e reutiliza vagas não postadas (com validação de links vivos)
    requeue_stats = db.verify_and_requeue_unused_jobs(
        link_verifier_func=verify_url_is_active
    )
    logger.info(f"Reutilização: {requeue_stats['reused']} vagas OK, {requeue_stats['removed_dead_links']} links mortos removidos")
    
    # Busca vagas para o canal FREE
    jobs_free = db.get_jobs_for_posting('free', JOBS_PER_DAY_FREE)
    logger.info(f"Vagas para canal FREE: {len(jobs_free)}")
    
    # Busca vagas para o canal PAID
    jobs_paid = db.get_jobs_for_posting('paid', JOBS_PER_DAY_PAID)
    logger.info(f"Vagas para canal PAID: {len(jobs_paid)}")
    
    # Posta no FREE
    posted_free = await post_jobs_to_free_channel(jobs_free)
    for job in posted_free:
        db.mark_as_posted(job['id'], 'free', job.get('posted_channel', ''), job.get('posted_message_id'))
    
    # Posta no PAID
    posted_paid = await post_jobs_to_paid_channel(jobs_paid)
    for job in posted_paid:
        db.mark_as_posted(job['id'], 'paid', job.get('posted_channel', ''), job.get('posted_message_id'))
    
    logger.info(f"Postadas: FREE={len(posted_free)}, PAID={len(posted_paid)}")
    return len(posted_free), len(posted_paid)


async def run_full_cycle():
    """Executa ciclo completo de curadoria"""
    logger.info("*" * 60)
    logger.info(f"INICIANDO CICLO COMPLETO - {datetime.now().isoformat()}")
    logger.info("*" * 60)
    
    stats = {}
    
    try:
        # Fase 1: Descoberta
        stats['discovered'] = await run_discovery()
        
        # Fase 2: Pré-filtro
        stats['prefiltered'] = await run_prefilter()
        
        # Fase 3: Análise
        approved, rejected = await run_analysis()
        stats['approved'] = approved
        stats['rejected'] = rejected
        
        # Fase 4: Link Resolver
        resolved, failed = await run_link_resolver()
        stats['links_resolved'] = resolved
        stats['links_failed'] = failed
        
        # Fase 5: Posting
        posted_free, posted_paid = await run_posting()
        stats['posted_free'] = posted_free
        stats['posted_paid'] = posted_paid
        
        # Estatísticas da fila
        queue_stats = db.get_queue_stats()
        stats.update({
            'queue_total': queue_stats['queue_total'],
            'queue_high': queue_stats['queue_high_salary'],
            'queue_low': queue_stats['queue_low_salary'],
        })
        
    except Exception as e:
        logger.error(f"ERRO NO CICLO: {e}")
        import traceback
        traceback.print_exc()
    
    logger.info("*" * 60)
    logger.info("CICLO COMPLETO FINALIZADO")
    logger.info(f"Stats: {stats}")
    logger.info("*" * 60)
    
    return stats


async def verify_queue_links():
    """
    Verifica se links na fila ainda estão ativos.
    Executa periodicamente para remover vagas fechadas.
    """
    logger.info("Verificando links na fila...")
    
    # Implementação futura: verificar links e remover inativos
    pass


def main():
    """Função principal com agendamento"""
    
    logger.info("🚀 Job Curator Bot iniciado!")
    logger.info(f"📂 Data dir: {DATA_DIR}")
    logger.info(f"⏰ Horários: {SCHEDULE_HOURS}")
    logger.info(f"📊 Limites: FREE={JOBS_PER_DAY_FREE}/dia, PAID={JOBS_PER_DAY_PAID}/dia")
    
    # Garante que o diretório de dados existe
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Agenda execuções
    for hour in SCHEDULE_HOURS:
        schedule.every().day.at(hour).do(
            lambda: asyncio.run(run_full_cycle())
        )
        logger.info(f"  Agendado para {hour}")
    
    # NÃO executa imediatamente - espera o horário agendado
    # Isso evita estourar rate limit ao reiniciar
    logger.info("Aguardando próximo horário agendado (sem ciclo inicial)...")
    
    # Loop de agendamento
    logger.info("Entrando em modo de agendamento...")
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
