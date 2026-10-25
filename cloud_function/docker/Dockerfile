FROM node:22-alpine

WORKDIR /app

# Install CLI tools once during image build for fast startup in Cloud Run
RUN npm install -g --loglevel=error --no-fund --no-audit --no-update-notifier @dbml/cli @liam-hq/cli && \
    rm -rf /root/.npm

# Copy all schemas and the server script
COPY schemas/ /app/schemas/
COPY cloud_function/server.js /app/cloud_function/server.js

# Pre-build all schemas from schemas/ directory for instant cold start in Cloud Run
RUN mkdir -p /app/dist-prebuilt && \
    for f in /app/schemas/*.dbml; do \
      if [ -f "$f" ]; then \
        name=$(basename "$f" .dbml); \
        dbml2sql "$f" --postgres -o "/tmp/${name}.sql" && \
        liam erd build --input "/tmp/${name}.sql" --format postgres --output-dir "/app/dist-prebuilt/${name}" && \
        sha256sum "$f" | awk '{print $1}' > "/app/dist-prebuilt/${name}/.schema_hash" && \
        rm -f "/tmp/${name}.sql"; \
      fi; \
    done

ENV PORT=8080
ENV LOCAL_ROOT_DIR=/app
EXPOSE 8080

CMD ["node", "/app/cloud_function/server.js"]
