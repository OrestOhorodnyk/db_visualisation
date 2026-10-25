import asyncio
import hashlib
import html
import json
import mimetypes
import os
import posixpath
import re
import shutil
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse

PORT = int(os.environ.get("PORT", "8080"))
SCHEMAS_DIR = os.environ.get("SCHEMAS_DIR", "schemas").strip("/")
LOCAL_ROOT_DIR = Path(
    os.environ.get("LOCAL_ROOT_DIR") or Path(__file__).resolve().parent.parent
)
DIST_ROOT = Path("/tmp/liam-builds")
PREBUILT_ROOT = Path("/app/dist-prebuilt")

# Git configuration for dynamically fetching schemas in GCP Cloud Run
GITHUB_REPO = (
    os.environ.get("GITHUB_REPO", "")
    .strip()
    .removeprefix("https://github.com/")
    .removeprefix("http://github.com/")
    .removesuffix(".git")
    .strip("/")
)  # e.g., "OrestOhorodnyk/db_visualisation"
GITLAB_PROJECT_ID = os.environ.get("GITLAB_PROJECT_ID", "")  # e.g., "123456" or "group/project"
GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
GIT_RAW_URL = os.environ.get("GIT_RAW_URL", "")  # URL template: https://.../raw/{branch}/{file}
GIT_TOKEN = os.environ.get("GIT_TOKEN", "")  # Personal Access Token (for private repositories)
DEFAULT_BRANCH = os.environ.get("GIT_BRANCH", "main")
DEFAULT_SCHEMA = os.environ.get("DEFAULT_SCHEMA", "")  # If empty, "/" renders a directory of all schemas
CACHE_TTL_SECONDS = float(os.environ.get("CACHE_TTL_SECONDS", "15"))

# Security settings for Confluence <iframe> embedding
FRAME_ANCESTORS = os.environ.get("FRAME_ANCESTORS", "'self' https://*.atlassian.net")
ACCESS_KEY = os.environ.get("ACCESS_KEY", "")

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
}

app = FastAPI(
    title="Liam ERD Multi-Schema Server",
    description="Dynamic DBML to Liam ERD server for GCP Cloud Run and Confluence iframes",
    docs_url="/api/docs",
    redoc_url=None,
)

# Async build cache indexed by f"{branch}:{file_path}"
build_state_cache: dict[str, dict] = {}
build_locks: dict[str, asyncio.Lock] = {}


def sha256_hex(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sanitize_key(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", value)


def get_key_lock(cache_key: str) -> asyncio.Lock:
    if cache_key not in build_locks:
        build_locks[cache_key] = asyncio.Lock()
    return build_locks[cache_key]


def normalize_schema_file(raw_input: str) -> str:
    """
    Resolves a short schema name (e.g., 'warehouse' or 'e_shop_schema')
    into a normalized relative repository path ('schemas/warehouse.dbml').
    """
    if not raw_input:
        return ""
    clean = raw_input.strip().lstrip("/")
    clean = posixpath.normpath(clean)
    while clean.startswith("../") or clean == "..":
        clean = clean[3:] if clean.startswith("../") else ""
    if not clean:
        return ""
    if not clean.endswith(".dbml"):
        clean += ".dbml"
    if "/" not in clean:
        clean = f"{SCHEMAS_DIR}/{clean}"
    return clean


async def list_available_schemas(branch: str) -> list[dict[str, str]]:
    """
    Returns a list of available .dbml schemas from GitHub, GitLab, or local schemas/ directory.
    """
    headers = {"User-Agent": "liam-erd-fastapi"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if GITHUB_REPO:
                if GIT_TOKEN:
                    headers["Authorization"] = f"Bearer {GIT_TOKEN}"
                headers["Accept"] = "application/vnd.github.v3+json"
                encoded_branch = urllib.parse.quote(branch, safe="")
                url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{SCHEMAS_DIR}?ref={encoded_branch}"
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    items = resp.json()
                    if isinstance(items, list):
                        return [
                            {"name": item["name"][:-5], "file": item["path"]}
                            for item in items
                            if item.get("type") == "file" and item.get("name", "").endswith(".dbml")
                        ]

            if GITLAB_PROJECT_ID:
                if GIT_TOKEN:
                    headers["PRIVATE-TOKEN"] = GIT_TOKEN
                encoded_proj = urllib.parse.quote(GITLAB_PROJECT_ID, safe="")
                encoded_dir = urllib.parse.quote(SCHEMAS_DIR, safe="")
                encoded_branch = urllib.parse.quote(branch, safe="")
                url = (
                    f"{GITLAB_URL}/api/v4/projects/{encoded_proj}/repository/tree"
                    f"?path={encoded_dir}&ref={encoded_branch}"
                )
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    items = resp.json()
                    if isinstance(items, list):
                        return [
                            {"name": item["name"][:-5], "file": item["path"]}
                            for item in items
                            if item.get("type") == "blob" and item.get("name", "").endswith(".dbml")
                        ]
    except Exception as exc:
        print(f"[Liam ERD] Warning listing remote schemas: {exc}", flush=True)

    # Fallback to local schemas/ directory
    local_dir = LOCAL_ROOT_DIR / SCHEMAS_DIR
    if local_dir.is_dir():
        files = sorted(
            f.name for f in local_dir.iterdir() if f.is_file() and f.name.endswith(".dbml")
        )
        return [{"name": fname[:-5], "file": f"{SCHEMAS_DIR}/{fname}"} for fname in files]

    return []


async def fetch_schema_dbml(branch: str, file_path: str) -> tuple[str, str]:
    """
    Fetches the latest content of a specific .dbml file from Git or local directory.
    Returns (content, source_description).
    """
    clean_file = normalize_schema_file(file_path)
    headers = {"User-Agent": "liam-erd-fastapi"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. GitHub REST API v3
        if GITHUB_REPO:
            if GIT_TOKEN:
                headers["Authorization"] = f"Bearer {GIT_TOKEN}"
            headers["Accept"] = "application/vnd.github.v3.raw"
            encoded_branch = urllib.parse.quote(branch, safe="")
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{clean_file}?ref={encoded_branch}"
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(
                    f'GitHub API error ({resp.status_code}) for "{clean_file}": {resp.text}'
                )
            return resp.text, f"github:{GITHUB_REPO}@{branch}:{clean_file}"

        # 2. GitLab REST API v4
        if GITLAB_PROJECT_ID:
            if GIT_TOKEN:
                headers["PRIVATE-TOKEN"] = GIT_TOKEN
            encoded_proj = urllib.parse.quote(GITLAB_PROJECT_ID, safe="")
            encoded_file = urllib.parse.quote(clean_file, safe="")
            encoded_branch = urllib.parse.quote(branch, safe="")
            url = (
                f"{GITLAB_URL}/api/v4/projects/{encoded_proj}/repository/files/"
                f"{encoded_file}/raw?ref={encoded_branch}"
            )
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(
                    f'GitLab API error ({resp.status_code}) for "{clean_file}": {resp.text}'
                )
            return resp.text, f"gitlab:{GITLAB_PROJECT_ID}@{branch}:{clean_file}"

        # 3. Raw URL template (supports {branch} and {file} placeholders)
        if GIT_RAW_URL:
            if GIT_TOKEN:
                headers["Authorization"] = f"Bearer {GIT_TOKEN}"
            url = GIT_RAW_URL.replace(
                "{branch}", urllib.parse.quote(branch, safe="")
            ).replace("{file}", clean_file)
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(
                    f'Raw URL fetch error ({resp.status_code}) for "{clean_file}": {resp.text}'
                )
            return resp.text, url

    # 4. Local file from the project directory
    full_local_path = LOCAL_ROOT_DIR / clean_file
    if not full_local_path.is_file():
        raise FileNotFoundError(f"Schema file not found: {clean_file}")
    return full_local_path.read_text(encoding="utf-8"), f"local:{clean_file}"


async def run_cli_command(args: list[str], cwd: Path) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    return (
        proc.returncode or 0,
        stdout_bytes.decode("utf-8", errors="replace"),
        stderr_bytes.decode("utf-8", errors="replace"),
    )


async def ensure_liam_build(
    branch: str, raw_file_path: str, force_refresh: bool = False
) -> dict:
    """
    Checks whether the .dbml file has changed and rebuilds Liam ERD for the schema if needed.
    """
    file_path = normalize_schema_file(raw_file_path)
    cache_key = f"{branch}:{file_path}"
    is_remote_git = bool(GITHUB_REPO or GITLAB_PROJECT_ID or GIT_RAW_URL)

    cached = build_state_cache.get(cache_key)
    now = time.time()
    if (
        cached
        and not force_refresh
        and is_remote_git
        and (now - cached["lastCheckedAt"]) < CACHE_TTL_SECONDS
        and Path(cached["outputDir"]).is_dir()
    ):
        return cached

    key_lock = get_key_lock(cache_key)
    async with key_lock:
        cached = build_state_cache.get(cache_key)
        now = time.time()
        if (
            cached
            and not force_refresh
            and is_remote_git
            and (now - cached["lastCheckedAt"]) < CACHE_TTL_SECONDS
            and Path(cached["outputDir"]).is_dir()
        ):
            return cached

        dbml_content, source = await fetch_schema_dbml(branch, file_path)
        current_hash = sha256_hex(dbml_content)

        if cached and cached["hash"] == current_hash and Path(cached["outputDir"]).is_dir():
            cached["lastCheckedAt"] = time.time()
            return cached

        schema_base_name = Path(file_path).stem
        prebuilt_dir = PREBUILT_ROOT / sanitize_key(schema_base_name)
        prebuilt_hash_file = prebuilt_dir / ".schema_hash"
        if prebuilt_hash_file.is_file():
            prebuilt_hash = prebuilt_hash_file.read_text(encoding="utf-8").strip()
            if prebuilt_hash == current_hash:
                state = {
                    "schema": schema_base_name,
                    "file": file_path,
                    "hash": current_hash,
                    "outputDir": str(prebuilt_dir),
                    "source": source,
                    "builtAt": datetime.now(timezone.utc).isoformat(),
                    "lastCheckedAt": time.time(),
                }
                build_state_cache[cache_key] = state
                return state

        target_dir = DIST_ROOT / sanitize_key(cache_key) / current_hash[:12]
        tmp_work_dir = Path(f"{target_dir}_tmp_{int(time.time() * 1000)}")
        tmp_work_dir.mkdir(parents=True, exist_ok=True)

        try:
            tmp_dbml_path = tmp_work_dir / "schema.dbml"
            tmp_tbls_path = tmp_work_dir / "schema.tbls.json"
            tmp_dist_dir = tmp_work_dir / "dist"
            converter_script = Path(__file__).resolve().parent / "dbml_to_tbls.js"

            tmp_dbml_path.write_text(dbml_content, encoding="utf-8")

            rc, out, err = await run_cli_command(
                ["node", str(converter_script), "schema.dbml", "schema.tbls.json"],
                cwd=tmp_work_dir,
            )
            if rc != 0 or not tmp_tbls_path.is_file():
                raise RuntimeError(
                    f'DBML syntax error in "{file_path}":\n{out}\n{err}'.strip()
                )

            rc, out, err = await run_cli_command(
                [
                    "liam",
                    "erd",
                    "build",
                    "--input",
                    "schema.tbls.json",
                    "--format",
                    "tbls",
                    "--output-dir",
                    str(tmp_dist_dir),
                ],
                cwd=tmp_work_dir,
            )
            if rc != 0 or not tmp_dist_dir.is_dir():
                raise RuntimeError(
                    f'Liam ERD build failed for "{file_path}":\n{out}\n{err}'.strip()
                )

            target_dir.parent.mkdir(parents=True, exist_ok=True)
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            shutil.move(str(tmp_dist_dir), str(target_dir))
        finally:
            shutil.rmtree(tmp_work_dir, ignore_errors=True)

        if (
            cached
            and not str(cached["outputDir"]).startswith(str(PREBUILT_ROOT))
            and cached["outputDir"] != str(target_dir)
        ):
            shutil.rmtree(cached["outputDir"], ignore_errors=True)

        state = {
            "schema": schema_base_name,
            "file": file_path,
            "hash": current_hash,
            "outputDir": str(target_dir),
            "source": source,
            "builtAt": datetime.now(timezone.utc).isoformat(),
            "lastCheckedAt": time.time(),
        }
        build_state_cache[cache_key] = state
        print(
            f'[Liam ERD] Built "{file_path}" ({source}) -> hash={current_hash[:8]}',
            flush=True,
        )
        return state


def inject_schema_context_into_html(
    html_content: str, file_path: str, branch: str, key: str, refresh: bool
) -> str:
    """
    Injects a client-side script into index.html so each Confluence <iframe>:
    1. Defaults to showMode=ALL_FIELDS if not specified in the URL.
    2. Requests its own schema.json even when multiple schemas are embedded side by side.
    3. Displays floating hover tooltips for table and column descriptions (Note / note).
    """
    injected_script = f"""<script>
(function() {{
  try {{
    var currentUrl = new URL(window.location.href);
    if (!currentUrl.searchParams.has('showMode')) {{
      currentUrl.searchParams.set('showMode', 'ALL_FIELDS');
      window.history.replaceState(null, '', currentUrl.toString());
    }}
  }} catch (e) {{}}
  var origFetch = window.fetch;
  var targetSchema = {json.dumps(file_path)};
  var targetBranch = {json.dumps(branch)};
  var targetKey = {json.dumps(key or "")};
  var targetRefresh = {json.dumps("1" if refresh else "")};
  window.fetch = function(input, init) {{
    if (typeof input === 'string' && input.indexOf('schema.json') !== -1) {{
      var sep = input.indexOf('?') !== -1 ? '&' : '?';
      input = input + sep + '__schema=' + encodeURIComponent(targetSchema) + '&__branch=' + encodeURIComponent(targetBranch);
      if (targetKey) input += '&__key=' + encodeURIComponent(targetKey);
      if (targetRefresh) input += '&refresh=1';
    }}
    return origFetch.call(this, input, init).then(function(res) {{
      if (typeof input === 'string' && input.indexOf('schema.json') !== -1) {{
        res.clone().json().then(function(data) {{
          window.__LIAM_SCHEMA_DATA__ = data;
        }}).catch(function() {{}});
      }}
      return res;
    }});
  }};

  window.addEventListener('DOMContentLoaded', function() {{
    var tip = document.createElement('div');
    tip.style.cssText = 'position:fixed;z-index:99999;pointer-events:none;background:rgba(15,23,42,0.96);color:#f8fafc;border:1px solid #334155;border-radius:8px;padding:8px 12px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;font-size:12px;line-height:1.45;max-width:320px;box-shadow:0 8px 24px rgba(0,0,0,0.45);display:none;';
    document.body.appendChild(tip);

    function hideTip() {{
      tip.style.display = 'none';
    }}

    document.addEventListener('mousemove', function(e) {{
      var schema = window.__LIAM_SCHEMA_DATA__;
      if (!schema || !schema.tables) return hideTip();
      var node = e.target && e.target.closest ? e.target.closest('.react-flow__node') : null;
      if (!node) return hideTip();

      var tableName = node.getAttribute('data-id');
      var table = tableName ? schema.tables[tableName] : null;
      if (!table) return hideTip();

      var matchedCol = null;
      var el = e.target;
      while (el && el !== node) {{
        var txt = (el.textContent || '').trim();
        if (table.columns && table.columns[txt]) {{
          matchedCol = table.columns[txt];
          break;
        }}
        if (el.children && el.children.length > 0 && el.children.length <= 4) {{
          var firstTxt = (el.children[0].textContent || '').trim();
          if (table.columns && table.columns[firstTxt]) {{
            matchedCol = table.columns[firstTxt];
            break;
          }}
        }}
        el = el.parentElement;
      }}

      var title = '';
      var comment = '';
      if (matchedCol && matchedCol.comment) {{
        title = table.name + '.' + matchedCol.name + (matchedCol.type ? ' (' + matchedCol.type + ')' : '');
        comment = matchedCol.comment;
      }} else if (!matchedCol && table.comment) {{
        title = 'Table: ' + table.name;
        comment = table.comment;
      }} else {{
        return hideTip();
      }}

      tip.innerHTML = '<div style="color:#38bdf8;font-weight:600;margin-bottom:3px;">' +
        title.replace(/</g, '&lt;') + '</div><div style="color:#e2e8f0;">' +
        comment.replace(/</g, '&lt;') + '</div>';
      tip.style.display = 'block';
      var x = Math.min(e.clientX + 14, window.innerWidth - 340);
      var y = Math.min(e.clientY + 14, window.innerHeight - 100);
      tip.style.left = Math.max(8, x) + 'px';
      tip.style.top = Math.max(8, y) + 'px';
    }});

    document.addEventListener('mousedown', hideTip);
    document.addEventListener('wheel', hideTip, {{ passive: true }});
  }});
}})();
</script>"""
    return html_content.replace("<head>", f"<head>\n{injected_script}", 1)


def render_schema_directory_html(
    schemas: list[dict[str, str]], branch: str, proto: str, host: str
) -> str:
    """
    Renders the root directory page listing all available schemas when ?schema=... is omitted.
    """
    base_url = f"{proto}://{host}"
    key_param = f"&key={urllib.parse.quote(ACCESS_KEY, safe='')}" if ACCESS_KEY else ""

    rows_html = []
    for s in schemas:
        encoded_name = urllib.parse.quote(s["name"], safe="")
        iframe_url = f"{base_url}/?schema={encoded_name}&showMode=ALL_FIELDS{key_param}"
        rows_html.append(
            f"""
      <div class="card">
        <div class="card-info">
          <h2>{html.escape(s["name"])}</h2>
          <code>{html.escape(s["file"])}</code>
        </div>
        <div class="card-actions">
          <input type="text" readonly value="{html.escape(iframe_url)}" onclick="this.select()" title="Confluence Iframe URL" />
          <a class="btn" href="/?schema={encoded_name}&showMode=ALL_FIELDS{key_param}">Open ERD →</a>
        </div>
      </div>"""
        )

    cards_section = (
        "\n".join(rows_html)
        if rows_html
        else "<p>No .dbml files found in schemas/ directory.</p>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>DB Schemas — Liam ERD</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 40px 20px; }}
    .container {{ max-width: 820px; margin: 0 auto; }}
    h1 {{ font-size: 24px; margin-bottom: 8px; }}
    p.sub {{ color: #94a3b8; margin-top: 0; margin-bottom: 28px; font-size: 14px; }}
    .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 18px 20px; margin-bottom: 14px; display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }}
    .card-info h2 {{ margin: 0 0 4px 0; font-size: 18px; color: #38bdf8; }}
    .card-info code {{ font-size: 12px; color: #94a3b8; }}
    .card-actions {{ display: flex; align-items: center; gap: 10px; flex: 1; justify-content: flex-end; min-width: 300px; }}
    input {{ background: #0f172a; border: 1px solid #334155; color: #cbd5e1; padding: 8px 10px; border-radius: 6px; font-family: monospace; font-size: 12px; width: 100%; max-width: 380px; }}
    .btn {{ background: #0284c7; color: #fff; text-decoration: none; padding: 8px 14px; border-radius: 6px; font-size: 13px; font-weight: 500; white-space: nowrap; }}
    .btn:hover {{ background: #0369a1; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Available DB Schemas (branch: <code>{html.escape(branch)}</code>)</h1>
    <p class="sub">Copy the URL for the Confluence <b>Iframe</b> macro or open the interactive diagram:</p>
    {cards_section}
  </div>
</body>
</html>"""


def resolve_target_params(
    request: Request, explicit_schema: Optional[str] = None
) -> tuple[str, str, bool]:
    qp = request.query_params
    schema_input = (
        explicit_schema
        or qp.get("__schema")
        or qp.get("schema")
        or qp.get("file")
        or ""
    )
    branch = qp.get("__branch") or qp.get("branch") or ""
    refresh = qp.get("refresh") == "1"

    referer = request.headers.get("referer")
    if (not schema_input or not branch) and referer:
        try:
            ref_parsed = urllib.parse.urlsplit(referer)
            ref_params = urllib.parse.parse_qs(ref_parsed.query)
            if not schema_input:
                schema_input = (
                    (ref_params.get("__schema") or [""])[0]
                    or (ref_params.get("schema") or [""])[0]
                    or (ref_params.get("file") or [""])[0]
                )
                ref_match = re.match(r"^/s/([^/]+)", ref_parsed.path)
                if not schema_input and ref_match:
                    schema_input = urllib.parse.unquote(ref_match.group(1))
            if not branch:
                branch = (ref_params.get("__branch") or [""])[0] or (
                    ref_params.get("branch") or [""]
                )[0]
            if not refresh:
                refresh = (ref_params.get("refresh") or [""])[0] == "1"
        except Exception:
            pass

    return (
        branch or DEFAULT_BRANCH,
        normalize_schema_file(schema_input or DEFAULT_SCHEMA),
        refresh,
    )


def is_authorized(request: Request) -> bool:
    if not ACCESS_KEY:
        return True
    qp = request.query_params
    if qp.get("key") == ACCESS_KEY or qp.get("__key") == ACCESS_KEY:
        return True

    referer = request.headers.get("referer")
    if referer:
        try:
            ref_parsed = urllib.parse.urlsplit(referer)
            ref_params = urllib.parse.parse_qs(ref_parsed.query)
            if (
                (ref_params.get("key") or [""])[0] == ACCESS_KEY
                or (ref_params.get("__key") or [""])[0] == ACCESS_KEY
            ):
                return True
        except Exception:
            pass

    return request.cookies.get("erd_key") == ACCESS_KEY


@app.middleware("http")
async def security_and_auth_middleware(request: Request, call_next):
    if not is_authorized(request):
        resp = PlainTextResponse(
            "Forbidden: Invalid or missing ?key= parameter", status_code=403
        )
    else:
        resp = await call_next(request)

    resp.headers["Content-Security-Policy"] = f"frame-ancestors {FRAME_ANCESTORS};"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    if ACCESS_KEY and request.query_params.get("key") == ACCESS_KEY:
        resp.set_cookie(
            key="erd_key",
            value=ACCESS_KEY,
            path="/",
            httponly=True,
            samesite="none",
            secure=True,
        )
    return resp


@app.get("/api/status")
async def api_status(request: Request):
    branch, file_path, refresh = resolve_target_params(request)
    schemas = await list_available_schemas(branch)
    active_build = (
        await ensure_liam_build(branch, file_path, refresh) if file_path else None
    )
    return JSONResponse(
        {
            "status": "ok",
            "branch": branch,
            "availableSchemas": schemas,
            "activeBuild": active_build,
        }
    )


async def serve_erd_or_asset(
    request: Request, asset_pathname: str, explicit_schema: Optional[str] = None
) -> Response:
    try:
        branch, file_path, refresh = resolve_target_params(request, explicit_schema)

        # Render schema directory when root "/" is requested without ?schema=...
        if not file_path and asset_pathname in ("/", ""):
            schemas = await list_available_schemas(branch)
            proto = request.headers.get("x-forwarded-proto", "http")
            host = request.headers.get("host", f"localhost:{PORT}")
            html_str = render_schema_directory_html(schemas, branch, proto, host)
            return HTMLResponse(
                content=html_str,
                headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
            )

        target_file = file_path
        if not target_file:
            schemas = await list_available_schemas(branch)
            if not schemas:
                raise FileNotFoundError("No .dbml schemas found in schemas/ directory")
            target_file = schemas[0]["file"]

        state = await ensure_liam_build(branch, target_file, refresh)
        output_dir = Path(state["outputDir"]).resolve()

        rel_path = urllib.parse.unquote(asset_pathname).lstrip("/")
        if not rel_path:
            rel_path = "index.html"

        candidate_path = (output_dir / rel_path).resolve()
        if not str(candidate_path).startswith(str(output_dir)) or not candidate_path.is_file():
            candidate_path = output_dir / "index.html"

        ext = candidate_path.suffix.lower()
        cache_header = (
            "no-store, no-cache, must-revalidate"
            if ext in (".json", ".html")
            else "public, max-age=86400"
        )

        if candidate_path.name == "index.html":
            raw_html = candidate_path.read_text(encoding="utf-8")
            key = request.query_params.get("key", "")
            final_html = inject_schema_context_into_html(
                raw_html, state["file"], branch, key, refresh
            )
            return HTMLResponse(
                content=final_html,
                headers={"Cache-Control": cache_header},
            )

        media_type = (
            MIME_TYPES.get(ext)
            or mimetypes.guess_type(str(candidate_path))[0]
            or "application/octet-stream"
        )
        return FileResponse(
            path=str(candidate_path),
            media_type=media_type,
            headers={"Cache-Control": cache_header},
        )
    except Exception as exc:
        print(f"[Liam ERD Error]: {exc}", flush=True)
        return PlainTextResponse(
            f"Failed to build/render schema:\n\n{exc}", status_code=500
        )


@app.get("/s/{schema_name}")
async def serve_clean_schema_root(schema_name: str, request: Request):
    return await serve_erd_or_asset(request, "/", explicit_schema=schema_name)


@app.get("/s/{schema_name}/{asset_path:path}")
async def serve_clean_schema_asset(schema_name: str, asset_path: str, request: Request):
    return await serve_erd_or_asset(request, f"/{asset_path}", explicit_schema=schema_name)


@app.get("/")
async def serve_root(request: Request):
    return await serve_erd_or_asset(request, "/")


@app.get("/{asset_path:path}")
async def serve_asset(asset_path: str, request: Request):
    return await serve_erd_or_asset(request, f"/{asset_path}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
