# DB Visualization — Docs-as-Code ERD for Confluence

An automated **Docs-as-Code** workflow for designing, versioning, and visualizing multiple database schemas using **DBML**, **Liam ERD**, **Docker**, and **GCP Cloud Run**, designed to be embedded into **Confluence `<iframe>`** pages.

```mermaid
sequenceDiagram
    participant Dev as VS Code
    participant Git as GitHub / GitLab (stores .dbml only)
    participant GCR as GCP Cloud Run (server.py + dbml_to_tbls.js + Liam CLI)
    participant Conf as Confluence <iframe>

    Dev->>Git: 1. Edit schemas/warehouse.dbml & git push
    Conf->>GCR: 2. GET /?schema=warehouse&showMode=ALL_FIELDS
    GCR->>Git: 3. Fetch raw schemas/warehouse.dbml via Git API (if GITHUB_REPO is set)
    Git-->>GCR: Return raw .dbml text
    Note over GCR: 4. Compare SHA-256 hash of .dbml<br/>If changed: convert .dbml -> tbls JSON + liam erd build<br/>inside Cloud Run to generate schema.json
    GCR-->>Conf: 5. Serve interactive Liam ERD SPA + schema.json
```

---

## Tools & Tech Stack

| Tool | License | Commercial Use | Role in Project |
| :--- | :--- | :--- | :--- |
| **[DBML Specification](https://dbml.dbdiagram.io/)** | **Apache-2.0** | ✅ Free | Database-agnostic DSL for defining tables, columns, enums, relationships, indexes, and documentation notes (`schemas/*.dbml`) across **Snowflake**, PostgreSQL, BigQuery, etc. |
| **[`@dbml/core` + `dbml_to_tbls.js`](https://github.com/holistics/dbml)** | **Apache-2.0** | ✅ Free | Parses `.dbml` files directly into `tbls` JSON format (`--format tbls`), preserving 100% of **Snowflake** (`VARIANT`, `OBJECT`, `ARRAY`, `NUMBER(38,0)`, `TIMESTAMP_NTZ`) and SQL data types verbatim. |
| **[Liam ERD (`@liam-hq/cli`)](https://github.com/liam-hq/liam)** | **Apache-2.0** | ✅ Free | Open-source generator that builds an interactive web-based Entity-Relationship Diagram (SPA) from the generated `tbls` JSON schema. |
| **[Python 3](https://www.python.org/) + [FastAPI](https://fastapi.tiangolo.com/)** | **PSF / MIT** | ✅ Free | Asynchronous Python web framework (`cloud_function/server.py`) powered by **Uvicorn** (BSD-3-Clause) and **HTTPX** (BSD-3-Clause) that dynamically fetches `.dbml` files from Git, caches builds by SHA-256 hash, isolates multiple schemas across Confluence `<iframe>` embeds, and injects hover tooltips. |
| **[`uv` (`ghcr.io/astral-sh/uv:python3.12-alpine`)](https://docs.astral.sh/uv/)** | **Apache-2.0 / MIT** | ✅ Free | Base container image providing pinned Python 3.12 and high-performance `uv` dependency management (`pyproject.toml` & `uv.lock`). |
| **[Node.js (`nodejs` / `npm` on Alpine)](https://nodejs.org/)** | **MIT** | ✅ Free | Runtime inside the container used to execute the `@dbml/cli` and `@liam-hq/cli` CLI tools. |
| **VS Code Extensions** (`bocovo.dbml-erd-visualizer`, `matt-meyers.vscode-dbml`) | **MIT** | ✅ Free | Local IDE syntax highlighting and live DBML diagram preview during schema authoring. |
| **Docker Engine / CLI & Buildx** | **Apache-2.0** | ✅ Free* | Container build and runtime tools (*see note below on Docker Desktop vs. open-source runtimes*). |
| **GCP Cloud Run & Cloud Build** | **Cloud Service (Pay-as-you-go)** | ✅ Free Tier / Paid | Serverless container runtime providing an HTTPS endpoint (`https://*.a.run.app`) that scales to zero when idle. |

### Licensing & Commercial Compliance Notes

* **No Paid SaaS Subscriptions Required for Diagramming:** Unlike hosted `dbdiagram.io` or `dbdocs.io` (which require paid per-user subscriptions for private schemas, table groups, or password protection), both **`@dbml/cli`** and **`@liam-hq/cli`** are licensed under the permissive **Apache-2.0 License**. They can be freely used, modified, and self-hosted inside commercial/enterprise environments without licensing fees.
* **Docker Licensing Note:**
  * **Docker Engine, Docker CLI, and Buildx** are open-source under **Apache-2.0** and completely free for any company size when used on Linux, in CI/CD, or on macOS via open-source runtimes like **Colima** or **Rancher Desktop**.
  * **Docker Desktop** (the GUI application) requires a paid subscription for organizations with more than 250 employees or more than \$10M in annual revenue.
* **Google Cloud Platform (GCP) Costs:**
  * **Cloud Run** includes an Always Free tier (2 million requests/month, 360,000 GB-seconds of memory, and 180,000 vCPU-seconds/month). Because the service scales down to `0` instances when nobody is viewing a Confluence page, internal team usage typically stays at **\$0.00/month**.
  * **Cloud Build** includes 120 free build-minutes per day.

---

## Project Structure

```text
db_visualisation/
├── schemas/
│   ├── e_shop_schema.dbml       # E-Commerce database schema
│   └── warehouse.dbml           # Warehouse Management System (WMS) schema
├── cloud_function/
│   ├── docker/
│   │   └── Dockerfile           # Production & local Docker image definition
│   ├── dbml_to_tbls.js          # Direct DBML -> tbls JSON converter (Snowflake/SQL type-preserving)
│   ├── pyproject.toml           # Python project metadata & dependencies (managed by uv)
│   ├── uv.lock                  # Reproducible dependency lockfile
│   └── server.py                # Async multi-schema FastAPI server
├── .dockerignore
└── README.md
```

---

## Local Usage (VS Code + Docker)

### 1. Recommended VS Code Extensions
For syntax highlighting and side-by-side preview while editing `.dbml` files in VS Code:
* **DBML Entity-Relationship Diagrams visualizer** (`bocovo.dbml-erd-visualizer`)
* **vscode-dbml** (`matt-meyers.vscode-dbml`)

### 2. Build the Docker Image
From the project root directory:

```bash
docker build -f cloud_function/docker/Dockerfile -t erd-liam .
```

> **Note for macOS (Homebrew Docker CLI):** If you see `DEPRECATED: The legacy builder is deprecated`, enable Docker Buildx:
> ```bash
> brew install docker-buildx
> mkdir -p ~/.docker/cli-plugins
> ln -sfn "$(brew --prefix)/opt/docker-buildx/bin/docker-buildx" ~/.docker/cli-plugins/docker-buildx
> ```

### 3. Run Locally with Live Reload on Refresh
Mount the local `schemas/` folder and `server.py` into the container so any edits saved in VS Code (`Cmd + S`) take effect immediately when you refresh the browser (no container restart needed):

```bash
docker run --rm -p 3002:8080 \
  -v "$(pwd)/schemas:/app/schemas:ro" \
  -v "$(pwd)/cloud_function/server.py:/app/cloud_function/server.py:ro" \
  erd-liam
```

### 4. Open in Browser
* **Schema Directory (lists all `.dbml` files with copyable Confluence URLs):**
  [http://localhost:3002/](http://localhost:3002/)
* **E-Shop Schema:**
  [http://localhost:3002/?schema=e_shop_schema&showMode=ALL_FIELDS](http://localhost:3002/?schema=e_shop_schema&showMode=ALL_FIELDS)
* **Warehouse Schema:**
  [http://localhost:3002/?schema=warehouse&showMode=ALL_FIELDS](http://localhost:3002/?schema=warehouse&showMode=ALL_FIELDS)
* **Build Status & Diagnostics API:**
  [http://localhost:3002/api/status](http://localhost:3002/api/status)

---

## Writing Schemas & Documentation Notes

1. **Adding a New Schema:**
   Create a new `<name>.dbml` file inside the `schemas/` folder (e.g., `schemas/crm.dbml`). It will automatically appear on the root directory page (`/`) and be accessible at `/?schema=crm&showMode=ALL_FIELDS`.
2. **Adding Table & Field Descriptions:**
   Use `note: '...'` on columns and `Note: '...'` inside tables:
   ```dbml
   Table warehouses {
     id integer [pk, increment, note: 'Primary warehouse identifier']
     code varchar(20) [unique, not null, note: 'Short facility code, e.g., WH-LWO-01']

     Note: 'Physical warehouse facilities and distribution centers'
   }
   ```
   Descriptions are visible both **on mouse hover (tooltip)** directly on the diagram canvas and **in the right-hand details panel** when clicking a table.

---

## Deploying to GCP Cloud Run (GitHub & GitLab Integration)

Because [`server.py`](file:///Users/orestohorodnyk/Documents/work_files/db_visualisation/cloud_function/server.py) dynamically fetches `.dbml` files from your Git repository on the fly, **you only need to deploy the service to GCP Cloud Run once**. Subsequent changes pushed to `schemas/*.dbml` in Git will automatically render in Confluence without redeploying the container.

### Supported Git Providers

1. **GitLab (GitLab.com & Self-Hosted GitLab Instances):**
   * Uses the official **GitLab REST API v4**:
     * Lists available schemas via `GET {GITLAB_URL}/api/v4/projects/{GITLAB_PROJECT_ID}/repository/tree?path=schemas&ref={branch}`
     * Fetches raw `.dbml` files via `GET {GITLAB_URL}/api/v4/projects/{GITLAB_PROJECT_ID}/repository/files/{file}/raw?ref={branch}`
   * **Token Setup:** In GitLab, navigate to **Settings → Access Tokens** (Project Access Token) or **User Settings → Personal Access Tokens** and create a token with the **`read_api`** (or `read_repository`) scope and **Reporter / Viewer** role.
   * **Project Identifier (`GITLAB_PROJECT_ID`):** Supports either the numeric Project ID (e.g., `5829104`) or the namespace/project path (e.g., `my-group/db-visualisation`).
   * **Self-Hosted GitLab (`GITLAB_URL`):** Defaults to `https://gitlab.com`. Set `GITLAB_URL=https://gitlab.your-company.com` for internal/self-managed GitLab servers.

2. **GitHub (GitHub.com):**
   * Uses the **GitHub REST API v3** (`GET https://api.github.com/repos/{GITHUB_REPO}/contents/{file}?ref={branch}`).
   * **Token Setup:** Create a Fine-Grained Personal Access Token with **Contents: Read-only** permission for your repository.

### Step 1. Build and Push the Image with Cloud Build
Run from the project root directory (replace `YOUR_GCP_PROJECT_ID` and `YOUR_REGION`, e.g., `europe-west1`):

```bash
gcloud builds submit \
  --config /dev/stdin \
  --substitutions=_IMAGE="gcr.io/YOUR_GCP_PROJECT_ID/erd-liam:latest" . <<EOF
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-f', 'cloud_function/docker/Dockerfile', '-t', '\${_IMAGE}', '.']
images:
  - '\${_IMAGE}'
EOF
```

### Step 2. Deploy the Cloud Run Service

#### Option A: Connect to a GitLab Repository (GitLab.com or Self-Hosted)
```bash
gcloud run deploy erd-liam \
  --image gcr.io/YOUR_GCP_PROJECT_ID/erd-liam:latest \
  --region europe-west1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 512Mi \
  --set-env-vars="GITLAB_PROJECT_ID=my-group/db-visualisation,GITLAB_URL=https://gitlab.com,GIT_BRANCH=main,SCHEMAS_DIR=schemas,GIT_TOKEN=glpat_YOUR_GITLAB_PAT,ACCESS_KEY=YOUR_CONFLUENCE_SECRET_KEY"
```

*(To test GitLab fetching locally with Docker before deploying to GCP):*
```bash
docker run --rm -p 3002:8080 \
  -e GITLAB_PROJECT_ID="my-group/db-visualisation" \
  -e GITLAB_URL="https://gitlab.com" \
  -e GIT_TOKEN="glpat_YOUR_GITLAB_PAT" \
  -e GIT_BRANCH="main" \
  erd-liam
```

#### Option B: Connect to a GitHub Repository
```bash
gcloud run deploy erd-liam \
  --image gcr.io/YOUR_GCP_PROJECT_ID/erd-liam:latest \
  --region europe-west1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 512Mi \
  --set-env-vars="GITHUB_REPO=YOUR_ORG/YOUR_REPO,GIT_BRANCH=main,SCHEMAS_DIR=schemas,GIT_TOKEN=ghp_YOUR_GITHUB_PAT,ACCESS_KEY=YOUR_CONFLUENCE_SECRET_KEY"
```

---

## Environment Variables Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PORT` | `8080` | HTTP port listened on by `server.py`. |
| `SCHEMAS_DIR` | `schemas` | Folder path in the repository containing `.dbml` files. |
| `GITHUB_REPO` | `""` | GitHub repository in `owner/repo` format for dynamic fetching. |
| `GITLAB_PROJECT_ID` | `""` | GitLab project ID or URL-encoded path (`group/project`). |
| `GITLAB_URL` | `https://gitlab.com` | Base URL for self-hosted or cloud GitLab instances. |
| `GIT_RAW_URL` | `""` | Custom raw file URL template supporting `{branch}` and `{file}` placeholders. |
| `GIT_TOKEN` | `""` | Personal Access Token (GitHub PAT or GitLab Token) with read access to repository contents. |
| `GIT_BRANCH` | `main` | Default Git branch to read schemas from when `?branch=` is not specified in the URL. |
| `DEFAULT_SCHEMA` | `""` | Optional default schema name. When empty, `/` displays the interactive schema directory. |
| `CACHE_TTL_SECONDS` | `15` | Seconds to cache remote Git checks before polling Git API again. |
| `ACCESS_KEY` | `""` | Optional shared secret required in `?key=...` to prevent unauthorized access outside Confluence. |
| `FRAME_ANCESTORS` | `'self' https://*.atlassian.net` | Allowed parent domains in the `Content-Security-Policy: frame-ancestors` header. |

---

## Embedding in Confluence `<iframe>`

1. Open your target Confluence page and insert the **Iframe** macro.
2. Configure the macro URL for the specific schema you want to display on that page:
   * **E-Shop Page:**
     ```text
     https://erd-liam-xxxxx-ew.a.run.app/?schema=e_shop_schema&showMode=ALL_FIELDS&key=YOUR_CONFLUENCE_SECRET_KEY
     ```
   * **Warehouse Page:**
     ```text
     https://erd-liam-xxxxx-ew.a.run.app/?schema=warehouse&showMode=ALL_FIELDS&key=YOUR_CONFLUENCE_SECRET_KEY
     ```
   * **Specific Feature Branch (e.g., for RFC / Architecture Review pages):**
     ```text
     https://erd-liam-xxxxx-ew.a.run.app/?schema=warehouse&branch=feat/new-lots&showMode=ALL_FIELDS&key=YOUR_CONFLUENCE_SECRET_KEY
     ```
3. Set **Width** to `100%` and **Height** to `800px`.

