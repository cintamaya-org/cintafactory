FROM mcr.microsoft.com/playwright:v1.56.1-noble

ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV NODE_ENV=production
ENV NPM_CONFIG_PREFIX=/usr/local
ENV PATH=/usr/local/bin:${PATH}

ARG LIKEC4_VER=latest

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends graphviz; \
    rm -rf /var/lib/apt/lists/*; \
    if [ -n "${LIKEC4_VER:-}" ]; then \
        npm install -g "likec4@${LIKEC4_VER}"; \
    else \
        npm install -g likec4; \
    fi; \
    LIKEC4_BIN="$(npm root -g)/.bin/likec4"; \
    if [ -f "$LIKEC4_BIN" ]; then \
        ln -sf "$LIKEC4_BIN" /usr/local/bin/likec4; \
    else \
        echo "likec4 binary not found at $LIKEC4_BIN"; \
        find /usr/local -type f -name likec4 -maxdepth 6 2>/dev/null || true; \
    fi; \
    rm -rf /root/.npm

WORKDIR /opt/likec4-worker
COPY worker/package.json ./
RUN npm install --omit=dev
COPY worker ./
RUN mkdir -p /data \
    && chown -R pwuser:pwuser /opt/likec4-worker /data

WORKDIR /data
USER pwuser

EXPOSE 4173 5173 24678 9000
