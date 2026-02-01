def format_job_message(job):
    """Formata vaga pra Telegram com validação rigorosa"""
    
    # Validações
    if not job.get('source_url') or job.get('source_url') == 'None':
        return None  # REJEITA sem link
    
    title = job.get('title', 'N/A')
    company = job.get('company', 'Unknown')
    salary = job.get('salary_inferred', '~USD 3-5k')  # Inferido
    level_casual = job.get('level_casual', 'Qualquer nível')
    desc = job.get('description', '')[:150]
    link = job.get('source_url', '')
    
    msg = f"""
🌍 VAGA REMOTA

📌 {title}
🏢 {company}

💰 {salary}/mês
📊 {level_casual}

📝 {desc}

🔗 APLICAR AQUI
{link}
""".strip()
    
    return msg

# Teste
test_job = {
    'title': 'Web Designer',
    'company': 'Tech Corp',
    'salary_inferred': '~USD 3-5k',
    'level_casual': 'Não precisa faculdade, experiência ajuda',
    'description': 'Design de interfaces web modernas',
    'source_url': 'https://boards.greenhouse.io/tech-corp/jobs/12345'
}

print(format_job_message(test_job))
