"""
Job Curator Bot - Telegram Poster
Posta vagas formatadas nos canais Free e Pago
"""
import asyncio
import logging
from typing import Optional, List

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from config import (
    TELEGRAM_TOKEN_FREE,
    TELEGRAM_TOKEN_PAID,
    TELEGRAM_CHANNEL_FREE,
    TELEGRAM_CHANNEL_PAID,
    JOBS_PER_DAY_FREE,
    JOBS_PER_DAY_PAID,
)

logger = logging.getLogger(__name__)


def format_job_message(job: dict) -> str:
    """
    Formata a mensagem da vaga para o Telegram.
    
    Formato:
    🎯 Título da Vaga
    🏢 Empresa
    📁 Categoria | 🌍 Localização
    💰 Salário (se disponível)
    
    📝 Resumo atraente
    
    🔗 Candidatar-se
    """
    
    # Análise (se disponível)
    analysis = job.get('analysis_result', {})
    if isinstance(analysis, str):
        import json
        try:
            analysis = json.loads(analysis)
        except:
            analysis = {}
    
    # Emoji da categoria
    category = analysis.get('categoria', job.get('category', 'Other'))
    category_emoji = {
        'Technology': '💻',
        'Marketing': '📈',
        'Design': '🎨',
        'Operations': '⚙️',
        'Sales': '💼',
        'Healthcare': '🏥',
        'Education': '📚',
        'AI/ML': '🤖',
        'Other': '📋',
    }.get(category, '💼')
    
    # Título
    title = analysis.get('titulo_pt', job.get('title', 'Vaga Remota'))
    
    # Empresa
    company = analysis.get('empresa', job.get('company', 'Empresa Internacional'))
    
    # Localização
    location = job.get('location', 'Remote/Worldwide')
    if location and len(location) > 30:
        location = location[:27] + '...'
    
    # Salário
    salary_str = ""
    salary_est = analysis.get('salario_estimado_usd_mes')
    if salary_est:
        salary_str = f"\n💰 ~USD ${salary_est:,}/mês"
    elif job.get('salary_min') or job.get('salary_max'):
        if job.get('salary_min') and job.get('salary_max'):
            salary_str = f"\n💰 USD ${job['salary_min']:,} - ${job['salary_max']:,}/ano"
        elif job.get('salary_min'):
            salary_str = f"\n💰 USD ${job['salary_min']:,}+/ano"
    
    # High salary badge
    is_high = analysis.get('is_high_salary', False)
    high_badge = " 🔥" if is_high else ""
    
    # Resumo
    resumo = analysis.get('resumo_pt', '')
    if not resumo and job.get('description'):
        resumo = job['description'][:150] + '...' if len(job['description']) > 150 else job['description']
    
    # Tags
    tags = analysis.get('tags', job.get('tags', []))
    if tags and isinstance(tags, list):
        tags_str = ' '.join([f"#{t.replace(' ', '')}" for t in tags[:3]])
    else:
        tags_str = ""
    
    # Link
    link = job.get('direct_url') or job.get('source_url', '')
    
    # Nível
    nivel = analysis.get('nivel', '')
    nivel_str = f" • {nivel}" if nivel and nivel != 'Qualquer' else ""
    
    # Monta mensagem
    message = f"{category_emoji} *{title}*{high_badge}\n"
    message += f"🏢 {company}\n"
    message += f"📁 {category}{nivel_str} | 🌍 {location}"
    message += salary_str
    message += f"\n\n_{resumo}_" if resumo else ""
    message += f"\n\n{tags_str}" if tags_str else ""
    message += f"\n\n🔗 [Candidatar-se]({link})"
    
    return message


async def post_job_to_channel(bot: Bot, channel_id: str, job: dict) -> Optional[str]:
    """
    Posta uma vaga em um canal do Telegram.
    
    Returns:
        message_id se sucesso, None se falha
    """
    message = format_job_message(job)
    
    try:
        result = await bot.send_message(
            chat_id=channel_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        return str(result.message_id)
    except TelegramError as e:
        logger.error(f"Erro ao postar no Telegram: {e}")
        # Tenta sem markdown se falhar
        try:
            message_plain = message.replace('*', '').replace('_', '').replace('[', '').replace(']', '')
            result = await bot.send_message(
                chat_id=channel_id,
                text=message_plain,
                disable_web_page_preview=True
            )
            return str(result.message_id)
        except:
            return None


async def post_jobs_to_free_channel(jobs: List[dict]) -> List[dict]:
    """Posta vagas no canal gratuito"""
    
    if not TELEGRAM_TOKEN_FREE or not TELEGRAM_CHANNEL_FREE:
        logger.error("Credenciais do canal FREE não configuradas")
        return []
    
    bot = Bot(token=TELEGRAM_TOKEN_FREE)
    posted = []
    
    for job in jobs[:JOBS_PER_DAY_FREE]:
        message_id = await post_job_to_channel(bot, TELEGRAM_CHANNEL_FREE, job)
        if message_id:
            job['posted_message_id'] = message_id
            job['posted_channel'] = 'free'
            posted.append(job)
            logger.info(f"✅ Postado (FREE): {job.get('title', 'N/A')[:40]}")
        else:
            logger.warning(f"❌ Falha ao postar (FREE): {job.get('title', 'N/A')[:40]}")
        
        await asyncio.sleep(2)  # Rate limiting
    
    return posted


async def post_jobs_to_paid_channel(jobs: List[dict]) -> List[dict]:
    """Posta vagas no canal pago"""
    
    token = TELEGRAM_TOKEN_PAID or TELEGRAM_TOKEN_FREE
    channel = TELEGRAM_CHANNEL_PAID
    
    if not token or not channel:
        logger.error("Credenciais do canal PAID não configuradas")
        return []
    
    bot = Bot(token=token)
    posted = []
    
    for job in jobs[:JOBS_PER_DAY_PAID]:
        message_id = await post_job_to_channel(bot, channel, job)
        if message_id:
            job['posted_message_id'] = message_id
            job['posted_channel'] = 'paid'
            posted.append(job)
            logger.info(f"✅ Postado (PAID): {job.get('title', 'N/A')[:40]}")
        else:
            logger.warning(f"❌ Falha ao postar (PAID): {job.get('title', 'N/A')[:40]}")
        
        await asyncio.sleep(1)  # Rate limiting (mais rápido no pago)
    
    return posted


def format_daily_summary(stats: dict) -> str:
    """Formata resumo diário para enviar ao admin"""
    
    return f"""📊 *Resumo do Curador de Vagas*

🔍 *Descoberta*
• Vagas encontradas: {stats.get('discovered', 0)}
• Pré-filtradas: {stats.get('prefiltered', 0)}

🧠 *Análise (Gemini)*
• Aprovadas: {stats.get('approved', 0)}
• Rejeitadas: {stats.get('rejected', 0)}

🔗 *Link Resolver*
• Links diretos encontrados: {stats.get('links_resolved', 0)}
• Links não resolvidos: {stats.get('links_failed', 0)}

📤 *Postagem*
• Canal FREE: {stats.get('posted_free', 0)}/{JOBS_PER_DAY_FREE}
• Canal PAID: {stats.get('posted_paid', 0)}/{JOBS_PER_DAY_PAID}

📦 *Fila*
• Vagas na fila: {stats.get('queue_total', 0)}
• High salary (>$4k): {stats.get('queue_high', 0)}
• Outras: {stats.get('queue_low', 0)}
"""
