# Job Curator Bot - Dockerfile
FROM python:3.11-slim

# Metadados
LABEL maintainer="M60/UDI"
LABEL description="Bot Curador de Vagas de Trabalho Remoto"
LABEL version="1.0"

# Variáveis de ambiente
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV TZ=America/Sao_Paulo
ENV DATA_DIR=/app/data

# Instala dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Diretório de trabalho
WORKDIR /app

# Copia requirements primeiro (cache de layers)
COPY requirements.txt .

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia código
COPY config.py .
COPY database.py .
COPY job_analyzer.py .
COPY link_resolver.py .
COPY telegram_poster.py .
COPY app.py .
COPY scrapers/ ./scrapers/

# Cria diretório de dados
RUN mkdir -p /app/data

# Volume para persistência
VOLUME ["/app/data"]

# Health check
HEALTHCHECK --interval=5m --timeout=10s --start-period=30s \
    CMD python -c "import database; print('OK')" || exit 1

# Executa
CMD ["python", "app.py"]
