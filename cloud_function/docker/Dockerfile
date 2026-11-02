FROM ghcr.io/astral-sh/uv:python3.12-alpine

WORKDIR /app

# Install Node.js & npm for the @liam-hq/cli build tool
RUN apk add --no-cache nodejs npm && \
    npm install -g --loglevel=error --no-fund --no-audit --no-update-notifier @liam-hq/cli && \
    rm -rf /root/.npm

# Install Python dependencies using uv from pyproject.toml and uv.lock
COPY cloud_function/pyproject.toml cloud_function/uv.lock /app/cloud_function/
RUN uv sync --frozen --no-dev --no-install-project --directory /app/cloud_function && \
    uv cache clean

ENV PATH="/app/cloud_function/.venv/bin:$PATH"

# Copy all DBML schemas (exported from dbt with dbterd), the DBML-to-tbls converter, and the FastAPI server script
COPY schemas/ /app/schemas/
COPY cloud_function/dbml_to_tbls.py cloud_function/server.py /app/cloud_function/

# Pre-build all schemas from schemas/*.dbml: DBML -> tbls JSON -> Liam ERD
RUN mkdir -p /app/dist-prebuilt && \
    for f in /app/schemas/*.dbml; do \
      if [ -f "$f" ]; then \
        name=$(basename "$f" .dbml); \
        python /app/cloud_function/dbml_to_tbls.py "$f" "/tmp/${name}.tbls.json" && \
        liam erd build --input "/tmp/${name}.tbls.json" --format tbls --output-dir "/app/dist-prebuilt/${name}" && \
        sha256sum "$f" | awk '{print $1}' > "/app/dist-prebuilt/${name}/.schema_hash" && \
        rm -f "/tmp/${name}.tbls.json"; \
      fi; \
    done

ENV PORT=8080
ENV LOCAL_ROOT_DIR=/app
EXPOSE 8080

CMD ["python", "-u", "/app/cloud_function/server.py"]
