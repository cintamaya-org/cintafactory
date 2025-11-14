# Base Python 3.12 (Debian Bookworm)
FROM python:3.12-bookworm

# Empêche Python de bufferiser et d’écrire des .pyc
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Paquets système utiles (postgres client, build, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl netcat-traditional \
 && rm -rf /var/lib/apt/lists/*

# Dossier de l'app
WORKDIR /app

# Installer deps Python
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

# Copier le code (le repo complet est rsync côté CI)
COPY . /app

# Entrypoint (migrations, collectstatic, etc.)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Switch to a non-root user for runtime safety
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /logs \
    && chown -R appuser:appuser /app /logs /entrypoint.sh \
    && chmod -R ug+rwX /app /logs \
    && chmod +x /entrypoint.sh
USER appuser

# Gunicorn par défaut ; override possible via docker-compose
ENV PORT=8000
EXPOSE 8000

CMD ["/entrypoint.sh"]
