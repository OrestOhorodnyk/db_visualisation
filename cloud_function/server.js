const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');

const execFileAsync = promisify(execFile);

const PORT = Number(process.env.PORT || 8080);
const SCHEMAS_DIR = (process.env.SCHEMAS_DIR || 'schemas').replace(/^\/+|\/+$/g, '');
const LOCAL_ROOT_DIR = process.env.LOCAL_ROOT_DIR || path.resolve(__dirname, '..');
const DIST_ROOT = '/tmp/liam-builds';
const PREBUILT_ROOT = '/app/dist-prebuilt';

// Git configuration for dynamically fetching schemas in GCP Cloud Run
const GITHUB_REPO = process.env.GITHUB_REPO || ''; // e.g., "owner/repo"
const GITLAB_PROJECT_ID = process.env.GITLAB_PROJECT_ID || ''; // e.g., "123456" or "group/project"
const GITLAB_URL = (process.env.GITLAB_URL || 'https://gitlab.com').replace(/\/$/, '');
const GIT_RAW_URL = process.env.GIT_RAW_URL || ''; // URL template: https://.../raw/{branch}/{file}
const GIT_TOKEN = process.env.GIT_TOKEN || ''; // Personal Access Token (for private repositories)
const DEFAULT_BRANCH = process.env.GIT_BRANCH || 'main';
const DEFAULT_SCHEMA = process.env.DEFAULT_SCHEMA || ''; // If empty, "/" renders a directory of all available schemas
const CACHE_TTL_MS = Number(process.env.CACHE_TTL_SECONDS || 15) * 1000;

// Security settings for Confluence <iframe> embedding
const FRAME_ANCESTORS = process.env.FRAME_ANCESTORS || "'self' https://*.atlassian.net";
const ACCESS_KEY = process.env.ACCESS_KEY || '';

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
};

// Build state cache indexed by `${branch}:${filePath}`
const buildStateCache = new Map();
const inFlightBuilds = new Map();

function sha256(content) {
  return crypto.createHash('sha256').update(content).digest('hex');
}

function sanitizeKey(str) {
  return str.replace(/[^a-zA-Z0-9_-]/g, '_');
}

/**
 * Resolves a short schema name (e.g., "warehouse" or "e_shop_schema")
 * into a full relative repository path ("schemas/warehouse.dbml")
 */
function normalizeSchemaFile(rawInput) {
  if (!rawInput) return '';
  let clean = rawInput.trim().replace(/^\/+/, '');
  // Prevent path traversal
  clean = path.posix.normalize(clean).replace(/^(\.\.(\/|$))+/, '');
  if (!clean.endsWith('.dbml')) {
    clean += '.dbml';
  }
  if (!clean.includes('/')) {
    clean = `${SCHEMAS_DIR}/${clean}`;
  }
  return clean;
}

/**
 * Returns a list of available .dbml schemas (from Git or local schemas/ directory)
 */
async function listAvailableSchemas(branch) {
  const headers = { 'User-Agent': 'liam-erd-cloud-run' };

  try {
    if (GITHUB_REPO) {
      if (GIT_TOKEN) headers['Authorization'] = `Bearer ${GIT_TOKEN}`;
      headers['Accept'] = 'application/vnd.github.v3+json';
      const url = `https://api.github.com/repos/${GITHUB_REPO}/contents/${SCHEMAS_DIR}?ref=${encodeURIComponent(branch)}`;
      const res = await fetch(url, { headers });
      if (res.ok) {
        const items = await res.json();
        if (Array.isArray(items)) {
          return items
            .filter((item) => item.type === 'file' && item.name.endsWith('.dbml'))
            .map((item) => ({
              name: item.name.replace(/\.dbml$/, ''),
              file: item.path,
            }));
        }
      }
    }

    if (GITLAB_PROJECT_ID) {
      if (GIT_TOKEN) headers['PRIVATE-TOKEN'] = GIT_TOKEN;
      const url = `${GITLAB_URL}/api/v4/projects/${encodeURIComponent(GITLAB_PROJECT_ID)}/repository/tree?path=${encodeURIComponent(SCHEMAS_DIR)}&ref=${encodeURIComponent(branch)}`;
      const res = await fetch(url, { headers });
      if (res.ok) {
        const items = await res.json();
        if (Array.isArray(items)) {
          return items
            .filter((item) => item.type === 'blob' && item.name.endsWith('.dbml'))
            .map((item) => ({
              name: item.name.replace(/\.dbml$/, ''),
              file: item.path,
            }));
        }
      }
    }
  } catch (err) {
    console.warn('[Liam ERD] Warning listing remote schemas:', err.message);
  }

  // Fallback to local schemas/ directory
  const localDir = path.join(LOCAL_ROOT_DIR, SCHEMAS_DIR);
  if (fs.existsSync(localDir)) {
    const files = await fs.promises.readdir(localDir);
    return files
      .filter((f) => f.endsWith('.dbml'))
      .sort()
      .map((f) => ({
        name: f.replace(/\.dbml$/, ''),
        file: `${SCHEMAS_DIR}/${f}`,
      }));
  }

  return [];
}

/**
 * Fetches the latest content of a specific .dbml file from Git or local directory
 */
async function fetchSchemaDbml(branch, filePath) {
  const cleanFile = normalizeSchemaFile(filePath);
  const headers = { 'User-Agent': 'liam-erd-cloud-run' };

  // 1. GitHub API
  if (GITHUB_REPO) {
    if (GIT_TOKEN) headers['Authorization'] = `Bearer ${GIT_TOKEN}`;
    headers['Accept'] = 'application/vnd.github.v3.raw';
    const url = `https://api.github.com/repos/${GITHUB_REPO}/contents/${cleanFile}?ref=${encodeURIComponent(branch)}`;
    const res = await fetch(url, { headers });
    if (!res.ok) {
      throw new Error(`GitHub API error (${res.status}) for "${cleanFile}": ${await res.text()}`);
    }
    return { content: await res.text(), source: `github:${GITHUB_REPO}@${branch}:${cleanFile}` };
  }

  // 2. GitLab API
  if (GITLAB_PROJECT_ID) {
    if (GIT_TOKEN) headers['PRIVATE-TOKEN'] = GIT_TOKEN;
    const url = `${GITLAB_URL}/api/v4/projects/${encodeURIComponent(GITLAB_PROJECT_ID)}/repository/files/${encodeURIComponent(cleanFile)}/raw?ref=${encodeURIComponent(branch)}`;
    const res = await fetch(url, { headers });
    if (!res.ok) {
      throw new Error(`GitLab API error (${res.status}) for "${cleanFile}": ${await res.text()}`);
    }
    return { content: await res.text(), source: `gitlab:${GITLAB_PROJECT_ID}@${branch}:${cleanFile}` };
  }

  // 3. Raw URL template (supports {branch} and {file} placeholders)
  if (GIT_RAW_URL) {
    if (GIT_TOKEN) headers['Authorization'] = `Bearer ${GIT_TOKEN}`;
    const url = GIT_RAW_URL
      .replace('{branch}', encodeURIComponent(branch))
      .replace('{file}', cleanFile);
    const res = await fetch(url, { headers });
    if (!res.ok) {
      throw new Error(`Raw URL fetch error (${res.status}) for "${cleanFile}": ${await res.text()}`);
    }
    return { content: await res.text(), source: url };
  }

  // 4. Local file from the project directory
  const fullLocalPath = path.join(LOCAL_ROOT_DIR, cleanFile);
  if (!fs.existsSync(fullLocalPath)) {
    throw new Error(`Schema file not found: ${cleanFile}`);
  }
  const content = await fs.promises.readFile(fullLocalPath, 'utf8');
  return { content, source: `local:${cleanFile}` };
}

/**
 * Checks whether the .dbml file has changed and rebuilds Liam ERD for the schema if needed
 */
async function ensureLiamBuild(branch, rawFilePath, forceRefresh = false) {
  const filePath = normalizeSchemaFile(rawFilePath);
  const cacheKey = `${branch}:${filePath}`;
  const now = Date.now();
  const cached = buildStateCache.get(cacheKey);

  const isRemoteGit = Boolean(GITHUB_REPO || GITLAB_PROJECT_ID || GIT_RAW_URL);

  if (
    cached &&
    !forceRefresh &&
    isRemoteGit &&
    now - cached.lastCheckedAt < CACHE_TTL_MS &&
    fs.existsSync(cached.outputDir)
  ) {
    return cached;
  }

  if (inFlightBuilds.has(cacheKey)) {
    return inFlightBuilds.get(cacheKey);
  }

  const buildPromise = (async () => {
    try {
      const { content: dbmlContent, source } = await fetchSchemaDbml(branch, filePath);
      const currentHash = sha256(dbmlContent);

      if (cached && cached.hash === currentHash && fs.existsSync(cached.outputDir)) {
        cached.lastCheckedAt = Date.now();
        return cached;
      }

      // Check if a matching pre-built bundle already exists in /app/dist-prebuilt/<schema_name>
      const schemaBaseName = path.basename(filePath, '.dbml');
      const prebuiltDir = path.join(PREBUILT_ROOT, sanitizeKey(schemaBaseName));
      const prebuiltHashFile = path.join(prebuiltDir, '.schema_hash');
      if (fs.existsSync(prebuiltHashFile)) {
        const prebuiltHash = (await fs.promises.readFile(prebuiltHashFile, 'utf8')).trim();
        if (prebuiltHash === currentHash) {
          const state = {
            schema: schemaBaseName,
            file: filePath,
            hash: currentHash,
            outputDir: prebuiltDir,
            source,
            builtAt: new Date().toISOString(),
            lastCheckedAt: Date.now(),
          };
          buildStateCache.set(cacheKey, state);
          return state;
        }
      }

      const targetDir = path.join(DIST_ROOT, sanitizeKey(cacheKey), currentHash.slice(0, 12));
      const tmpWorkDir = `${targetDir}_tmp_${Date.now()}`;
      await fs.promises.mkdir(tmpWorkDir, { recursive: true });

      const tmpDbmlPath = path.join(tmpWorkDir, 'schema.dbml');
      const tmpSqlPath = path.join(tmpWorkDir, 'schema.sql');
      const tmpDistDir = path.join(tmpWorkDir, 'dist');

      await fs.promises.writeFile(tmpDbmlPath, dbmlContent, 'utf8');
      const dbmlResult = await execFileAsync(
        'dbml2sql',
        ['schema.dbml', '--postgres', '-o', 'schema.sql'],
        { cwd: tmpWorkDir }
      );
      if (!fs.existsSync(tmpSqlPath)) {
        throw new Error(
          `DBML syntax error in "${filePath}":\n${dbmlResult.stdout || ''}\n${dbmlResult.stderr || ''}`.trim()
        );
      }
      await execFileAsync(
        'liam',
        [
          'erd',
          'build',
          '--input',
          'schema.sql',
          '--format',
          'postgres',
          '--output-dir',
          tmpDistDir,
        ],
        { cwd: tmpWorkDir }
      );

      await fs.promises.mkdir(path.dirname(targetDir), { recursive: true });
      if (fs.existsSync(targetDir)) {
        await fs.promises.rm(targetDir, { recursive: true, force: true });
      }
      await fs.promises.rename(tmpDistDir, targetDir);
      await fs.promises.rm(tmpWorkDir, { recursive: true, force: true });

      if (cached && !cached.outputDir.startsWith(PREBUILT_ROOT) && cached.outputDir !== targetDir) {
        fs.promises.rm(cached.outputDir, { recursive: true, force: true }).catch(() => {});
      }

      const state = {
        schema: schemaBaseName,
        file: filePath,
        hash: currentHash,
        outputDir: targetDir,
        source,
        builtAt: new Date().toISOString(),
        lastCheckedAt: Date.now(),
      };
      buildStateCache.set(cacheKey, state);
      console.log(`[Liam ERD] Built "${filePath}" (${source}) -> hash=${currentHash.slice(0, 8)}`);
      return state;
    } finally {
      inFlightBuilds.delete(cacheKey);
    }
  })();

  inFlightBuilds.set(cacheKey, buildPromise);
  return buildPromise;
}

/**
 * Extracts target schema/file and branch from URL (?schema=warehouse, ?file=..., or /s/warehouse)
 */
function resolveTargetParams(reqUrl, req) {
  let schemaInput =
    reqUrl.searchParams.get('__schema') ||
    reqUrl.searchParams.get('schema') ||
    reqUrl.searchParams.get('file');
  let branch = reqUrl.searchParams.get('__branch') || reqUrl.searchParams.get('branch');
  let refresh = reqUrl.searchParams.get('refresh') === '1';

  // Support clean URL paths like /s/warehouse or /s/e_shop_schema
  const pathMatch = reqUrl.pathname.match(/^\/s\/([^/]+)(\/.*)?$/);
  let assetPathname = reqUrl.pathname;
  if (pathMatch) {
    if (!schemaInput) schemaInput = decodeURIComponent(pathMatch[1]);
    assetPathname = pathMatch[2] || '/';
  }

  // When the browser requests /schema.json or static assets, read target params from Referer
  if ((!schemaInput || !branch) && req.headers.referer) {
    try {
      const refUrl = new URL(req.headers.referer);
      if (!schemaInput) {
        schemaInput =
          refUrl.searchParams.get('__schema') ||
          refUrl.searchParams.get('schema') ||
          refUrl.searchParams.get('file');
        const refMatch = refUrl.pathname.match(/^\/s\/([^/]+)/);
        if (!schemaInput && refMatch) {
          schemaInput = decodeURIComponent(refMatch[1]);
        }
      }
      if (!branch) {
        branch = refUrl.searchParams.get('__branch') || refUrl.searchParams.get('branch');
      }
      if (!refresh) {
        refresh = refUrl.searchParams.get('refresh') === '1';
      }
    } catch {
      // ignore invalid referer
    }
  }

  return {
    branch: branch || DEFAULT_BRANCH,
    file: normalizeSchemaFile(schemaInput || DEFAULT_SCHEMA),
    refresh,
    assetPathname,
  };
}

/**
 * Validates optional ACCESS_KEY for securing Confluence <iframe> access
 */
function isAuthorized(reqUrl, req) {
  if (!ACCESS_KEY) return true;
  if (
    reqUrl.searchParams.get('key') === ACCESS_KEY ||
    reqUrl.searchParams.get('__key') === ACCESS_KEY
  ) {
    return true;
  }
  if (req.headers.referer) {
    try {
      const refUrl = new URL(req.headers.referer);
      if (
        refUrl.searchParams.get('key') === ACCESS_KEY ||
        refUrl.searchParams.get('__key') === ACCESS_KEY
      ) {
        return true;
      }
    } catch {
      // ignore
    }
  }
  const cookies = req.headers.cookie || '';
  return cookies.split(';').some((c) => c.trim() === `erd_key=${ACCESS_KEY}`);
}

/**
 * Injects a script into index.html so each Confluence <iframe> reliably requests its own schema.json
 * and defaults to showMode=ALL_FIELDS even when multiple schemas are open simultaneously
 */
function injectSchemaContextIntoHtml(htmlContent, file, branch, key, refresh) {
  const injectedScript = `<script>
(function() {
  try {
    var currentUrl = new URL(window.location.href);
    if (!currentUrl.searchParams.has('showMode')) {
      currentUrl.searchParams.set('showMode', 'ALL_FIELDS');
      window.history.replaceState(null, '', currentUrl.toString());
    }
  } catch (e) {}
  var origFetch = window.fetch;
  var targetSchema = ${JSON.stringify(file)};
  var targetBranch = ${JSON.stringify(branch)};
  var targetKey = ${JSON.stringify(key || '')};
  var targetRefresh = ${JSON.stringify(refresh ? '1' : '')};
  window.fetch = function(input, init) {
    if (typeof input === 'string' && input.indexOf('schema.json') !== -1) {
      var sep = input.indexOf('?') !== -1 ? '&' : '?';
      input = input + sep + '__schema=' + encodeURIComponent(targetSchema) + '&__branch=' + encodeURIComponent(targetBranch);
      if (targetKey) input += '&__key=' + encodeURIComponent(targetKey);
      if (targetRefresh) input += '&refresh=1';
    }
    return origFetch.call(this, input, init).then(function(res) {
      if (typeof input === 'string' && input.indexOf('schema.json') !== -1) {
        res.clone().json().then(function(data) {
          window.__LIAM_SCHEMA_DATA__ = data;
        }).catch(function() {});
      }
      return res;
    });
  };

  window.addEventListener('DOMContentLoaded', function() {
    var tip = document.createElement('div');
    tip.style.cssText = 'position:fixed;z-index:99999;pointer-events:none;background:rgba(15,23,42,0.96);color:#f8fafc;border:1px solid #334155;border-radius:8px;padding:8px 12px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;font-size:12px;line-height:1.45;max-width:320px;box-shadow:0 8px 24px rgba(0,0,0,0.45);display:none;';
    document.body.appendChild(tip);

    function hideTip() {
      tip.style.display = 'none';
    }

    document.addEventListener('mousemove', function(e) {
      var schema = window.__LIAM_SCHEMA_DATA__;
      if (!schema || !schema.tables) return hideTip();
      var node = e.target && e.target.closest ? e.target.closest('.react-flow__node') : null;
      if (!node) return hideTip();

      var tableName = node.getAttribute('data-id');
      var table = tableName ? schema.tables[tableName] : null;
      if (!table) return hideTip();

      var matchedCol = null;
      var el = e.target;
      while (el && el !== node) {
        var txt = (el.textContent || '').trim();
        if (table.columns && table.columns[txt]) {
          matchedCol = table.columns[txt];
          break;
        }
        if (el.children && el.children.length > 0 && el.children.length <= 4) {
          var firstTxt = (el.children[0].textContent || '').trim();
          if (table.columns && table.columns[firstTxt]) {
            matchedCol = table.columns[firstTxt];
            break;
          }
        }
        el = el.parentElement;
      }

      var title = '';
      var comment = '';
      if (matchedCol && matchedCol.comment) {
        title = table.name + '.' + matchedCol.name + (matchedCol.type ? ' (' + matchedCol.type + ')' : '');
        comment = matchedCol.comment;
      } else if (!matchedCol && table.comment) {
        title = 'Table: ' + table.name;
        comment = table.comment;
      } else {
        return hideTip();
      }

      tip.innerHTML = '<div style="color:#38bdf8;font-weight:600;margin-bottom:3px;">' +
        title.replace(/</g, '&lt;') + '</div><div style="color:#e2e8f0;">' +
        comment.replace(/</g, '&lt;') + '</div>';
      tip.style.display = 'block';
      var x = Math.min(e.clientX + 14, window.innerWidth - 340);
      var y = Math.min(e.clientY + 14, window.innerHeight - 100);
      tip.style.left = Math.max(8, x) + 'px';
      tip.style.top = Math.max(8, y) + 'px';
    });

    document.addEventListener('mousedown', hideTip);
    document.addEventListener('wheel', hideTip, { passive: true });
  });
})();
</script>`;
  return htmlContent.replace('<head>', `<head>\n${injectedScript}`);
}

/**
 * Renders the root directory page listing all available schemas when ?schema=... is omitted
 */
function renderSchemaDirectoryHtml(schemas, branch, req) {
  const proto = req.headers['x-forwarded-proto'] || 'http';
  const host = req.headers.host || `localhost:${PORT}`;
  const baseUrl = `${proto}://${host}`;
  const keyParam = ACCESS_KEY ? `&key=${encodeURIComponent(ACCESS_KEY)}` : '';

  const rows = schemas
    .map((s) => {
      const iframeUrl = `${baseUrl}/?schema=${encodeURIComponent(s.name)}&showMode=ALL_FIELDS${keyParam}`;
      return `
      <div class="card">
        <div class="card-info">
          <h2>${s.name}</h2>
          <code>${s.file}</code>
        </div>
        <div class="card-actions">
          <input type="text" readonly value="${iframeUrl}" onclick="this.select()" title="Confluence Iframe URL" />
          <a class="btn" href="/?schema=${encodeURIComponent(s.name)}&showMode=ALL_FIELDS${keyParam}">Open ERD →</a>
        </div>
      </div>`;
    })
    .join('\n');

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>DB Schemas — Liam ERD</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 40px 20px; }
    .container { max-width: 820px; margin: 0 auto; }
    h1 { font-size: 24px; margin-bottom: 8px; }
    p.sub { color: #94a3b8; margin-top: 0; margin-bottom: 28px; font-size: 14px; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 18px 20px; margin-bottom: 14px; display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
    .card-info h2 { margin: 0 0 4px 0; font-size: 18px; color: #38bdf8; }
    .card-info code { font-size: 12px; color: #94a3b8; }
    .card-actions { display: flex; align-items: center; gap: 10px; flex: 1; justify-content: flex-end; min-width: 300px; }
    input { background: #0f172a; border: 1px solid #334155; color: #cbd5e1; padding: 8px 10px; border-radius: 6px; font-family: monospace; font-size: 12px; width: 100%; max-width: 380px; }
    .btn { background: #0284c7; color: #fff; text-decoration: none; padding: 8px 14px; border-radius: 6px; font-size: 13px; font-weight: 500; white-space: nowrap; }
    .btn:hover { background: #0369a1; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Available DB Schemas (branch: <code>${branch}</code>)</h1>
    <p class="sub">Copy the URL for the Confluence <b>Iframe</b> macro or open the interactive diagram:</p>
    ${rows || '<p>No .dbml files found in schemas/ directory.</p>'}
  </div>
</body>
</html>`;
}

const server = http.createServer(async (req, res) => {
  try {
    const reqUrl = new URL(req.url, `http://${req.headers.host || 'localhost'}`);

    // Security headers for Confluence <iframe> embedding
    res.setHeader('Content-Security-Policy', `frame-ancestors ${FRAME_ANCESTORS};`);
    res.setHeader('Access-Control-Allow-Origin', '*');

    if (!isAuthorized(reqUrl, req)) {
      res.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('Forbidden: Invalid or missing ?key= parameter');
      return;
    }

    if (ACCESS_KEY && reqUrl.searchParams.get('key') === ACCESS_KEY) {
      res.setHeader('Set-Cookie', `erd_key=${ACCESS_KEY}; Path=/; HttpOnly; SameSite=None; Secure`);
    }

    const { branch, file, refresh, assetPathname } = resolveTargetParams(reqUrl, req);

    // Diagnostic endpoint returning available schemas and active build metadata
    if (reqUrl.pathname === '/api/status') {
      const schemas = await listAvailableSchemas(branch);
      const activeBuild = file ? await ensureLiamBuild(branch, file, refresh) : null;
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(
        JSON.stringify(
          {
            status: 'ok',
            branch,
            availableSchemas: schemas,
            activeBuild,
          },
          null,
          2
        )
      );
      return;
    }

    // Render schema directory when root "/" is requested without ?schema=...
    if (!file && (reqUrl.pathname === '/' || reqUrl.pathname === '')) {
      const schemas = await listAvailableSchemas(branch);
      const html = renderSchemaDirectoryHtml(schemas, branch, req);
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(html);
      return;
    }

    // For static asset requests (/assets/...) when file is not explicitly set, use the first available schema build
    let targetFile = file;
    if (!targetFile) {
      const schemas = await listAvailableSchemas(branch);
      if (schemas.length === 0) {
        throw new Error('No .dbml schemas found in schemas/ directory');
      }
      targetFile = schemas[0].file;
    }

    const state = await ensureLiamBuild(branch, targetFile, refresh);

    let relativePath = decodeURIComponent(assetPathname);
    if (relativePath === '/' || relativePath === '') {
      relativePath = '/index.html';
    }

    const safeSuffix = path.normalize(relativePath).replace(/^(\.\.(\/|\\|$))+/, '');
    let filePath = path.join(state.outputDir, safeSuffix);

    if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
      filePath = path.join(state.outputDir, 'index.html');
    }

    const ext = path.extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';

    if (ext === '.json' || ext === '.html') {
      res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate');
    } else {
      res.setHeader('Cache-Control', 'public, max-age=86400');
    }

    if (path.basename(filePath) === 'index.html') {
      const rawHtml = await fs.promises.readFile(filePath, 'utf8');
      const key = reqUrl.searchParams.get('key') || '';
      const html = injectSchemaContextIntoHtml(rawHtml, state.file, branch, key, refresh);
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(html);
      return;
    }

    const content = await fs.promises.readFile(filePath);
    res.writeHead(200, { 'Content-Type': contentType });
    res.end(content);
  } catch (err) {
    console.error('[Liam ERD Error]:', err);
    res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end(`Failed to build/render schema:\n\n${err.message}`);
  }
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`[Liam ERD Server] Listening on http://0.0.0.0:${PORT}`);
});
