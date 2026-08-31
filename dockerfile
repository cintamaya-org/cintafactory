# ==========================================
# ÉTAPE 1 : BUILDER (Compilation)
# ==========================================
FROM python:3.12-bookworm AS builder

ENV UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Utilitaires de compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
 && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN /root/.local/bin/uv sync --frozen --no-dev

# ==========================================
# ÉTAPE 2 : PRODUCTION (Runtime sécurisé)
# ==========================================
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Uniquement les dépendances d'exécution (base de données et réseau)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 netcat-traditional \
 && rm -rf /var/lib/apt/lists/*

# Création de l'utilisateur non-root pour la sécurité
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app /logs \
    && chown -R appuser:appuser /app /logs

WORKDIR /app

# Copie de l'environnement Python compilé à l'étape 1
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# Copie du code source et de l'entrypoint
COPY --chown=appuser:appuser . /app
COPY --chown=appuser:appuser cintafactory/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

USER appuser
EXPOSE 8000

CMD ["/entrypoint.sh"]