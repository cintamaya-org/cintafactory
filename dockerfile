 syntax=docker/dockerfile:1

# ============================================================
# Stage 1 — Build : image DHI "dev" (shell + outils de build)
# ============================================================
FROM dhi.io/python:3.12-debian13-dev AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# uv + dépendances système nécessaires à la compilation (psycopg2, cryptography...)
# L'image -dev inclut apt, donc ça fonctionne ici. Elle n'existera plus dans le runtime final.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev

COPY . /app

# ============================================================
# Stage 2 — Runtime : image DHI hardened (sans shell, sans apt)
# ============================================================
FROM dhi.io/python:3.12-debian13 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    PORT=8000

WORKDIR /app

# On ne copie QUE le venv et le code applicatif — rien des outils de build.
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

# Les images DHI tournent déjà en non-root par défaut (pas besoin de USER appuser).

EXPOSE 8000

# Pas de shell disponible -> CMD en exec form direct, pas de script bash.
# Migrations et collectstatic : gérés par un Job/initContainer Kubernetes
# séparé (voir manifests K8s), plus par un entrypoint.sh dans l'image.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "cintafactory.wsgi:application"]
# Gunicorn par défaut ; override possible via docker-compose
ENV PORT=8000
EXPOSE 8000

CMD ["/entrypoint.sh"]
