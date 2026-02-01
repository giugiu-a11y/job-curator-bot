"""
Job Curator Bot - Job Analyzer (Gemini via Akira-Pipe)
Analisa vagas com os critérios M60/UDI

Otimizado para batch analysis - 1 chamada para múltiplas vagas via Akira-Pipe.
"""
import os
import json
import time
import subprocess # Added for calling akira-pipe
import logging
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

import anthropic # Kept as per user directive

# Carrega .env
load_dotenv(Path(__file__).parent / '.env')

from config import (
    CLAUDE_API_KEY, # Kept as per user directive
    SALARY_HIGH_THRESHOLD,
    REJECTION_TERMS,
    JOB_CATEGORIES
)

logger = logging.getLogger(__name__)

# Path to the akira-pipe script
AKIRA_PIPE_PATH = "/home/ubuntu/clawd/bin/akira-pipe"

# Prompt do sistema com critérios M60
SYSTEM_PROMPT = f"""Você é um curador especialista em vagas de trabalho remoto para brasileiros que querem trabalhar para empresas internacionais.

## SUA TAREFA
Analise a vaga abaixo e decida se deve ser APROVADA ou REJEITADA com base nos critérios da M60/UDI.

## CRITÉRIOS DE REJEIÇÃO IMEDIATA (se qualquer um for verdadeiro, REJEITE)

### 1. Restrição Geográfica
REJEITAR se contiver QUALQUER um destes termos (ou variações):
{', '.join(f'"{t}"' for t in REJECTION_TERMS[:10])}
... e similares.

A vaga deve aceitar candidatos internacionais/globais OU não mencionar restrição.

### 2. Esquemas Suspeitos
REJEITAR se for:
- MLM / Marketing multinível
- Comissão pura sem salário base
- "Seja seu próprio chefe" / esquemas de pirâmide
- Vagas muito vagas sem empresa identificável

### 3. Vagas Genéricas
REJEITAR se:
- Não identificar claramente a empresa
- For um "pool" de candidatos sem vaga específica

## CRITÉRIOS DE APROVAÇÃO

### 1. Geografia Aceita
- Worldwide / Global / Remote / Anywhere
- USA, Canadá, Europa, Ásia, Austrália, NZ
- LATAM / Brasil (se empresa internacional)
- Não menciona restrição geográfica específica

### 2. Salário
- Priorizar vagas > USD ${SALARY_HIGH_THRESHOLD}/mês
- Mas aceitar vagas menores se cumprirem outros requisitos
- Inferir salário se possível (ex: "competitive salary for senior role" = provavelmente > $4k)

### 3. Mix de Acessibilidade
Aceitar diversidade:
- Com e sem inglês fluente exigido
- Com e sem diploma universitário
- Diferentes níveis de experiência

## CATEGORIAS
Classifique em uma destas: {', '.join(JOB_CATEGORIES)}

## FORMATO DE RESPOSTA
Responda APENAS com JSON válido, sem markdown:

{{
    "aprovada": true/false,
    "motivo_rejeicao": "string explicando porque foi rejeitada, ou null se aprovada",
    "accepts_international": true/false,
    "categoria": "uma das categorias listadas",
    "nivel": "Junior|Pleno|Senior|Lead|Executive|Qualquer",
    "requer_ingles_fluente": true/false/null,
    "requer_diploma": true/false/null,
    "salario_estimado_usd_mes": numero ou null,
    "is_high_salary": true se > ${SALARY_HIGH_THRESHOLD}/mês (real ou inferido),
    "empresa": "Nome da empresa",
    "titulo_pt": "Título traduzido para português",
    "resumo_pt": "Resumo atraente de 1-2 linhas em português (máx 150 chars)",
    "tags": ["lista", "de", "tags", "relevantes"],
    "confianca": 0.0-1.0 (quão confiante você está na análise)
}}

IMPORTANTE:
- Responda APENAS o JSON, sem texto adicional
- Se não tiver certeza sobre salário, infira com base no cargo/senioridade
- O resumo deve ser profissional mas atraente para brasileiros"""


# Prompt otimizado para batch (múltiplas vagas em 1 chamada)
BATCH_SYSTEM_PROMPT = f"""Você é um curador especialista em vagas de trabalho remoto para brasileiros que querem trabalhar para empresas internacionais.

## SUA TAREFA
Analise TODAS as vagas abaixo e decida para CADA UMA se deve ser APROVADA ou REJEITADA.

## CRITÉRIOS DE REJEIÇÃO IMEDIATA (se qualquer um for verdadeiro, REJEITE)

### 1. Restrição Geográfica
REJEITAR se contiver QUALQUER um destes termos (ou variações):
{', '.join(f'"{t}"' for t in REJECTION_TERMS[:10])}
... e similares.

A vaga deve aceitar candidatos internacionais/globais OU não mencionar restrição.

### 2. Esquemas Suspeitos
REJEITAR se for MLM, comissão pura sem salário, ou "seja seu próprio chefe".

### 3. Vagas Genéricas
REJEITAR se não identificar claramente a empresa ou for "pool" de candidatos.

## CRITÉRIOS DE APROVAÇÃO
- Worldwide / Global / Remote / Anywhere
- USA, Canadá, Europa, Ásia, Austrália, NZ, LATAM, Brasil (se empresa internacional)
- Priorizar vagas > USD ${SALARY_HIGH_THRESHOLD}/mês mas aceitar menores se cumprirem requisitos

## CATEGORIAS
{', '.join(JOB_CATEGORIES)}

## FORMATO DE RESPOSTA
Responda com um JSON ARRAY contendo a análise de CADA vaga, na MESMA ORDEM das vagas enviadas.
APENAS o JSON, sem markdown, sem texto adicional:

[
  {{
    "job_index": 0,
    "aprovada": true/false,
    "motivo_rejeicao": "string ou null se aprovada",
    "accepts_international": true/false,
    "categoria": "categoria",
    "nivel": "Junior|Pleno|Senior|Lead|Executive|Qualquer",
    "requer_ingles_fluente": true/false/null,
    "requer_diploma": true/false/null,
    "salario_estimado_usd_mes": numero ou null,
    "is_high_salary": true/false,
    "empresa": "Nome da empresa",
    "titulo_pt": "Título em português",
    "resumo_pt": "Resumo de 1-2 linhas (máx 150 chars)",
    "tags": ["tags"],
    "confianca": 0.0-1.0
  }},
  ... (uma entrada para cada vaga)
]

IMPORTANTE:
- Responda APENAS o JSON array
- Uma entrada para CADA vaga, na mesma ordem
- job_index deve corresponder à ordem das vagas (0, 1, 2, ...)"""


def init_claude():
    """Inicializa o cliente Claude"""
    # Kept as per user directive, but not used in current analysis logic
    if not CLAUDE_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY não configurada")
    return anthropic.Anthropic(api_key=CLAUDE_API_KEY)


def _format_job_text(job: dict, truncate_desc: int = 2000) -> str:
    """Formata uma vaga para texto de análise."""
    return f"""TÍTULO: {job.get('title', 'N/A')}
EMPRESA: {job.get('company', 'N/A')}
LOCALIZAÇÃO: {job.get('location', 'N/A')}
FONTE: {job.get('source_url', 'N/A')}
DESCRIÇÃO: {job.get('description', 'N/A')[:truncate_desc]}"""


# Removed _clean_json_response as akira-pipe's decide.py will handle JSON output directly


def analyze_job(job: dict, client=None) -> Optional[dict]:
    """
    Analisa uma vaga com Gemini via Akira-Pipe.
    
    Args:
        job: dict com dados da vaga (title, company, description, etc)
        client: (Ignorado) instância do cliente Anthropic, mantida para compatibilidade.
    
    Returns:
        dict com resultado da análise ou None se falhar
    """
    job_text = _format_job_text(job, truncate_desc=4000)
    
    # Task para o akira-pipe, incluindo o SYSTEM_PROMPT e formato de resposta
    task_instruction = f"{SYSTEM_PROMPT}"
    prompt_payload = json.dumps({
        "clean_text": job_text,
        "meta": {"job_id": job.get('id')},
        "task": task_instruction
    }, ensure_ascii=False)

    try:
        logger.info(f"Análise via Akira-Pipe para job {job.get('id')}")
        process = subprocess.run(
            [AKIRA_PIPE_PATH],
            input=prompt_payload.encode('utf-8'),
            capture_output=True,
            text=True, # Decodes stdout/stderr as text
            check=False # Do not raise an exception for non-zero exit codes
        )

        if process.returncode != 0:
            logger.error(f"Akira-Pipe ERRO para job {job.get('id')}: {process.stderr.strip()}")
            # Tenta parsear o stdout mesmo em erro, se contiver JSON de erro
            try:
                error_output = json.loads(process.stdout.strip())
                return {
                    'job_id': job.get('id'),
                    'analyzed': False,
                    'aprovada': False,
                    'motivo_rejeicao': f'Akira-Pipe Error: {error_output.get('error', 'Unknown')}'
                }
            except json.JSONDecodeError:
                return {
                    'job_id': job.get('id'),
                    'analyzed': False,
                    'aprovada': False,
                    'motivo_rejeicao': f'Akira-Pipe Error: {process.stderr.strip()[:100]}'
                }

        # Processou com sucesso
        pipeline_result = json.loads(process.stdout.strip())
        if not pipeline_result.get('ok'):
            logger.error(f"Akira-Pipe reportou falha para job {job.get('id')}: {pipeline_result.get('error', 'Unknown')}")
            return {
                'job_id': job.get('id'),
                'analyzed': False,
                'aprovada': False,
                'motivo_rejeicao': f'Akira-Pipe Failed: {pipeline_result.get('error', 'Unknown')}'
            }
        
        result = pipeline_result.get('result')
        if not result:
            logger.error(f"Akira-Pipe não retornou resultado válido para job {job.get('id')}")
            return {
                'job_id': job.get('id'),
                'analyzed': False,
                'aprovada': False,
                'motivo_rejeicao': 'Akira-Pipe: Resultado vazio'
            }
        
        result['job_id'] = job.get('id')
        result['analyzed'] = True
        
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao parsear JSON do Akira-Pipe para job {job.get('id')}: {e}")
        return {
            'job_id': job.get('id'),
            'analyzed': False,
            'aprovada': False,
            'motivo_rejeicao': f'JSON Parse Error: {str(e)[:50]}'
        }
    except Exception as e:
        logger.error(f"Erro ao analisar job {job.get('id')} via Akira-Pipe: {e}")
        return {
            'job_id': job.get('id'),
            'analyzed': False,
            'aprovada': False,
            'motivo_rejeicao': f'Unexpected Error: {str(e)[:50]}'
        }


def batch_analyze_jobs_single_call(jobs: list, client=None) -> list:
    """
    Analisa múltiplas vagas em UMA ÚNICA chamada ao Gemini via Akira-Pipe.
    Otimizado para reduzir tokens - 5 vagas = 1 API call para o pipeline.
    
    Args:
        jobs: lista de dicts com dados das vagas (máx recomendado: 5)
        client: (Ignorado) instância do cliente Anthropic, mantida para compatibilidade.
    
    Returns:
        lista de resultados de análise (mesma ordem das vagas)
    """
    if not jobs:
        return []
    
    # Monta prompt com todas as vagas numeradas
    jobs_text_parts = []
    for i, job in enumerate(jobs):
        job_text = _format_job_text(job, truncate_desc=1500)  # Menor para caber mais vagas
        jobs_text_parts.append(f"=== VAGA {i} ===\n{job_text}")
    
    combined_job_text = chr(10).join(jobs_text_parts)
    task_instruction = f"""{BATCH_SYSTEM_PROMPT}
\nAnalise as {len(jobs)} vagas abaixo e retorne um JSON array com a análise de CADA uma, na mesma ordem das vagas enviadas.\nAPENAS o JSON ARRAY, sem markdown, sem texto adicional."""

    prompt_payload = json.dumps({
        "clean_text": combined_job_text,
        "meta": {"job_ids": [job.get('id') for job in jobs]},
        "task": task_instruction
    }, ensure_ascii=False)

    all_results = []

    try:
        logger.info(f"Batch analysis via Akira-Pipe: {len(jobs)} vagas em 1 chamada")
        process = subprocess.run(
            [AKIRA_PIPE_PATH],
            input=prompt_payload.encode('utf-8'),
            capture_output=True,
            text=True,
            check=False
        )

        if process.returncode != 0:
            logger.error(f"Akira-Pipe ERRO em batch para {len(jobs)} vagas: {process.stderr.strip()}")
            # Tenta parsear o stdout mesmo em erro
            try:
                error_output = json.loads(process.stdout.strip())
                return [{
                    'job_id': job.get('id'),
                    'analyzed': False,
                    'aprovada': False,
                    'motivo_rejeicao': f'Akira-Pipe Batch Error: {error_output.get('error', 'Unknown')}'
                } for job in jobs] # Retorna erro para todas as vagas no batch
            except json.JSONDecodeError:
                return [{
                    'job_id': job.get('id'),
                    'analyzed': False,
                    'aprovada': False,
                    'motivo_rejeicao': f'Akira-Pipe Batch Error: {process.stderr.strip()[:100]}'
                } for job in jobs]

        # Processou com sucesso
        pipeline_result = json.loads(process.stdout.strip())
        if not pipeline_result.get('ok'):
            logger.error(f"Akira-Pipe reportou falha em batch para {len(jobs)} vagas: {pipeline_result.get('error', 'Unknown')}")
            return [{
                'job_id': job.get('id'),
                'analyzed': False,
                'aprovada': False,
                'motivo_rejeicao': f'Akira-Pipe Batch Failed: {pipeline_result.get('error', 'Unknown')}'
            } for job in jobs]

        results = pipeline_result.get('result')
        if not isinstance(results, list):
            logger.error(f"Akira-Pipe não retornou um ARRAY JSON para batch de {len(jobs)} vagas. Tentando wrap...")
            results = [results] if results else [] # Tenta embrulhar em lista se não for
        
        # Associa job_ids e valida ordem
        final_results = []
        for i, job in enumerate(jobs):
            if i < len(results):
                result = results[i]
                result['job_id'] = job.get('id')
                result['analyzed'] = True
                final_results.append(result)
                
                status = "✅" if result.get('aprovada') else "❌"
                logger.info(f"  [{i}] {status} {job.get('title', 'N/A')[:40]}")
            else:
                # Akira-Pipe não retornou análise para esta vaga
                logger.warning(f"  [{i}] ⚠️ Sem análise para: {job.get('title', 'N/A')[:40]}")
                final_results.append({
                    'job_id': job.get('id'),
                    'analyzed': False,
                    'aprovada': False,
                    'motivo_rejeicao': 'Akira-Pipe: Análise não retornada'
                })
        
        # Estatísticas
        approved = sum(1 for r in final_results if r.get('aprovada'))
        rejected = len(final_results) - approved
        logger.info(f"Batch concluído: {approved} aprovadas, {rejected} rejeitadas (1 API call para Akira-Pipe)")
        
        return final_results
        
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao parsear JSON batch do Akira-Pipe: {e}")
        return [{
            'job_id': job.get('id'),
            'analyzed': False,
            'aprovada': False,
            'motivo_rejeicao': f'Batch JSON Parse Error: {str(e)[:50]}'
        } for job in jobs]
    except Exception as e:
        logger.error(f"Erro na análise batch via Akira-Pipe: {e}")
        return [{
            'job_id': job.get('id'),
            'analyzed': False,
            'aprovada': False,
            'motivo_rejeicao': f'Unexpected Batch Error: {str(e)[:50]}'
        } for job in jobs]


def batch_analyze_jobs(jobs: list, client=None, batch_size: int = 5) -> list:
    """
    Analisa múltiplas vagas usando batch otimizado via Akira-Pipe.
    Agrupa em lotes de batch_size e faz 1 chamada por lote.
    
    Args:
        jobs: lista de dicts com dados das vagas
        client: (Ignorado) instância do cliente Anthropic, mantida para compatibilidade.
        batch_size: quantas vagas por chamada (default: 5)
    
    Returns:
        lista de resultados de análise
    """
    # if client is None: # No longer needed as client is not used
    #     client = init_claude()
    
    all_results = []
    
    # Processa em lotes
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(jobs) + batch_size - 1) // batch_size
        
        logger.info(f"[Batch {batch_num}/{total_batches}] Processando {len(batch)} vagas...")
        
        # Call the new batch_analyze_jobs_single_call which uses akira-pipe
        results = batch_analyze_jobs_single_call(batch)
        all_results.extend(results)
        
        # Rate limiting entre batches (não entre vagas individuais)
        if i + batch_size < len(jobs):
            time.sleep(1)  # 1s entre batches é suficiente
    
    # Estatísticas finais
    approved = sum(1 for r in all_results if r.get('aprovada'))
    rejected = len(all_results) - approved
    api_calls = (len(jobs) + batch_size - 1) // batch_size
    logger.info(f"Total: {approved} aprovadas, {rejected} rejeitadas ({api_calls} chamadas Akira-Pipe para {len(jobs)} vagas)")
    
    return all_results


def quick_reject_check(job: dict) -> Optional[str]:
    """
    Verificação rápida de rejeição (sem usar IA).
    Útil para pré-filtrar antes de gastar tokens do Claude.
    
    Returns:
        None se passou no pré-filtro, ou string com motivo de rejeição
    """
    text_to_check = ' '.join([
        job.get('title', ''),
        job.get('description', ''),
        job.get('location', ''),
    ]).lower()
    
    # Verifica termos de rejeição
    for term in REJECTION_TERMS:
        if term.lower() in text_to_check:
            return f"Termo de rejeição encontrado: {term}"
    
    return None  # Passou no pré-filtro
