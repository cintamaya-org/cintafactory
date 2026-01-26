// Minimal Node server to edit a C4 file and view the LikeC4 diagram side by side.
const { createServer } = require('http');
const { access, mkdir, writeFile, readdir, unlink } = require('fs').promises;
const { createReadStream } = require('fs');
const { createHash } = require('crypto');
const { extname, join, basename, dirname, posix, resolve, sep } = require('path');

const PORT = process.env.LIKEC4_EDITOR_PORT || 4173;
const ROOT_DIR = __dirname; // always resolve relative to where server.js lives
const DEFAULT_STORAGE_PATH = (process.env.C4_FILE || 'likec4/default.c4').replace(/^\/+/, '');
const PREVIEW_DIR = process.env.LIKEC4_PREVIEW_DIR || '/tmp/likec4-previews';
const SEAWEEDFS_FILER_URL = (process.env.SEAWEEDFS_FILER_URL || '').replace(/\/+$/, '');
const SEAWEEDFS_BASE_DIR = (process.env.SEAWEEDFS_BASE_DIR || '').replace(/^\/+|\/+$/g, '');
const LIKEC4_METADATA_URL = process.env.LIKEC4_METADATA_URL || '';
const LIKEC4_METADATA_TOKEN = process.env.LIKEC4_METADATA_TOKEN || 'dev_token_idHaf';
const LIKEC4_API_TOKEN = (process.env.LIKEC4_API_TOKEN || 'dev_likec4_api_token_change_me').trim();
const PUBLIC_DIR = join(ROOT_DIR, 'ui');
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
};

const encodeSeaweedPath = (path) => {
  const clean = path.replace(/^\/+/, '');
  const full = SEAWEEDFS_BASE_DIR ? `${SEAWEEDFS_BASE_DIR}/${clean}` : clean;
  return full
    .split('/')
    .map(segment => encodeURIComponent(segment))
    .join('/');
};

const buildSeaweedUrl = (path) => {
  if (!SEAWEEDFS_FILER_URL) {
    throw new Error('SEAWEEDFS_FILER_URL not configured');
  }
  return `${SEAWEEDFS_FILER_URL}/${encodeSeaweedPath(path)}`;
};

const readFromSeaweed = async (path) => {
  const url = buildSeaweedUrl(path);
  const response = await fetch(url, { method: 'GET' });
  if (response.status === 404) {
    return { content: '', missing: true };
  }
  if (!response.ok) {
    throw new Error(`SeaweedFS read failed (${response.status})`);
  }
  const content = await response.text();
  const contentType = response.headers.get('content-type') || 'text/plain';
  return { content, contentType };
};

const writeToSeaweed = async (path, content) => {
  const url = buildSeaweedUrl(path);
  const payload = Buffer.from(content ?? '', 'utf8');
  const response = await fetch(url, {
    method: 'PUT',
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Content-Length': String(payload.length),
    },
    body: payload,
  });
  if (!response.ok) {
    throw new Error(`SeaweedFS write failed (${response.status})`);
  }
  return {
    size: payload.length,
    contentType: 'text/plain',
  };
};

const postMetadata = async ({ filePath, size, contentType }) => {
  if (!LIKEC4_METADATA_URL) {
    console.warn('LikeC4 metadata URL not configured; skipping metadata update.');
    return;
  }
  const headers = { 'Content-Type': 'application/json' };
  const url = LIKEC4_METADATA_URL;
  try {
    console.log(`Posting LikeC4 metadata for ${filePath} -> ${url}`);
    const payload = {
      path: filePath,
      size,
      content_type: contentType,
    };
    if (LIKEC4_METADATA_TOKEN) {
      headers['X-LikeC4-Token'] = LIKEC4_METADATA_TOKEN;
      payload.token = LIKEC4_METADATA_TOKEN;
    }
    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const body = await response.text().catch(() => '');
      console.warn(`LikeC4 metadata update failed (${response.status}) ${body}`);
    } else {
      console.log(`LikeC4 metadata update ok (${response.status})`);
    }
  } catch (err) {
    console.warn(`LikeC4 metadata update failed: ${err.message}`);
  }
};

const getFileParam = (req) => {
  try {
    const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
    return url.searchParams.get('file');
  } catch {
    return null;
  }
};

const getAuthToken = (req) => {
  const header = req.headers.authorization || '';
  if (header.toLowerCase().startsWith('bearer ')) {
    return header.slice(7).trim();
  }
  const tokenHeader = req.headers['x-likec4-token'];
  if (tokenHeader) {
    return String(tokenHeader).trim();
  }
  try {
    const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
    return url.searchParams.get('token') || '';
  } catch {
    return '';
  }
};

const requireApiAuth = (req, res) => {
  if (!LIKEC4_API_TOKEN) {
    send(res, 500, 'Server not configured');
    return false;
  }
  const provided = getAuthToken(req);
  if (!provided || provided !== LIKEC4_API_TOKEN) {
    send(res, 401, 'Unauthorized');
    return false;
  }
  return true;
};

const normalizeStoragePath = (raw) => {
  if (!raw) {
    return DEFAULT_STORAGE_PATH;
  }
  const cleaned = String(raw)
    .trim()
    .replace(/\\/g, '/')
    .replace(/^\/+/, '');
  if (!cleaned) {
    return DEFAULT_STORAGE_PATH;
  }
  if (cleaned.includes(':')) {
    return DEFAULT_STORAGE_PATH;
  }
  const rawParts = cleaned.split('/').filter(Boolean);
  if (!rawParts.length || rawParts.some(part => part === '.' || part === '..')) {
    return DEFAULT_STORAGE_PATH;
  }
  const normalized = posix.normalize(rawParts.join('/'));
  const parts = normalized.split('/').filter(Boolean);
  if (!parts.length || parts.some(part => part === '.' || part === '..')) {
    return DEFAULT_STORAGE_PATH;
  }
  if (!normalized.toLowerCase().endsWith('.c4')) {
    return DEFAULT_STORAGE_PATH;
  }
  return parts.join('/');
};

const safePublicPath = (rawPath) => {
  const cleaned = String(rawPath || '')
    .replace(/\\/g, '/')
    .replace(/^\/+/, '');
  if (!cleaned) return '';
  const segments = cleaned.split('/').filter(Boolean);
  if (!segments.length || segments.some(segment => segment === '.' || segment === '..')) {
    return '';
  }
  const normalized = posix.normalize(segments.join('/'));
  if (!normalized || normalized === '.' || normalized.startsWith('..') || normalized.includes('/..') || normalized.includes(':')) {
    return '';
  }
  const resolvedBase = resolve(PUBLIC_DIR);
  const resolvedTarget = resolve(PUBLIC_DIR, normalized);
  if (resolvedTarget === resolvedBase || !resolvedTarget.startsWith(`${resolvedBase}${sep}`)) {
    return '';
  }
  return resolvedTarget;
};

const slugifySegment = (value) =>
  String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'diagram';

const canonicalLikeC4Path = (rawPath) => {
  const normalized = normalizeStoragePath(rawPath);
  if (normalized.startsWith('diagrams/')) {
    return normalized;
  }
  const base = posix.basename(normalized || 'diagram.c4').replace(/\.c4$/i, '');
  const folder = slugifySegment(base);
  return `diagrams/${folder}/likec4.c4`;
};

const resolveStoragePaths = (req) => {
  const rawParam = getFileParam(req);
  const hasParam = rawParam !== null && rawParam !== undefined && String(rawParam).trim() !== '';
  const normalized = normalizeStoragePath(rawParam);
  const canonical = hasParam ? canonicalLikeC4Path(normalized) : normalized;
  return { requested: normalized, canonical, hasParam };
};

const readLikeC4Content = async (requestedPath, canonicalPath) => {
  let result = await readFromSeaweed(requestedPath);
  let usedPath = requestedPath;
  if (result.missing && canonicalPath && canonicalPath !== requestedPath) {
    const fallback = await readFromSeaweed(canonicalPath);
    if (!fallback.missing) {
      result = fallback;
      usedPath = canonicalPath;
    }
  }
  return { ...result, path: usedPath };
};

const previewNameFor = (storagePath) => {
  const hash = createHash('sha256').update(storagePath || DEFAULT_STORAGE_PATH, 'utf8').digest('hex');
  return `${hash}.c4`;
};

const previewPathFor = (storagePath) => join(PREVIEW_DIR, previewNameFor(storagePath));

const prunePreviewFiles = async (keepFileName) => {
  if (!keepFileName) return;
  try {
    const entries = await readdir(PREVIEW_DIR, { withFileTypes: true });
    const removals = entries.filter((entry) =>
      entry.isFile() && entry.name.endsWith('.c4') && entry.name !== keepFileName,
    );
    if (!removals.length) return;
    await Promise.all(removals.map((entry) =>
      unlink(join(PREVIEW_DIR, entry.name)).catch((err) => {
        console.warn(`Cannot remove preview file ${entry.name}: ${err.message}`);
      }),
    ));
  } catch (err) {
    if (err && err.code !== 'ENOENT') {
      console.warn(`Cannot prune preview files: ${err.message}`);
    }
  }
};

const syncPreviewFile = async (content, filePath) => {
  const previewName = previewNameFor(filePath);
  const target = join(PREVIEW_DIR, previewName);
  try {
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, content ?? '', 'utf8');
  } catch (err) {
    console.warn(`Cannot update preview file ${target}: ${err.message}`);
  }
  await prunePreviewFiles(previewName);
  return previewName;
};


const stripComments = (text) =>
  text
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .map(line => line.replace(/\/\/.*$/, ''))
    .join('\n');

const findClosingBrace = (text, openIndex) => {
  let depth = 0;
  let inSingle = false;
  let inDouble = false;
  for (let i = openIndex; i < text.length; i++) {
    const ch = text[i];
    const prev = i > 0 ? text[i - 1] : '';
    if (ch === '\'' && !inDouble && prev !== '\\') {
      inSingle = !inSingle;
    } else if (ch === '"' && !inSingle && prev !== '\\') {
      inDouble = !inDouble;
    }
    if (inSingle || inDouble) continue;
    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
};

const parseKeyValues = (text) => {
  const kv = /([A-Za-z_][\w-]*)\s+'([\s\S]*?)'/g;
  const entries = [];
  let match;
  while ((match = kv.exec(text)) !== null) {
    entries.push({ key: match[1], value: match[2].trim() });
  }
  return entries;
};

const parseComponents = (content, alreadyCleaned = false) => {
  const cleaned = alreadyCleaned ? content : stripComments(content);
  const components = [];
  const compRegex = /component\s+([A-Za-z_][\w-]*)\s*'([^']*)'\s*\{/g;
  let match;

  while ((match = compRegex.exec(cleaned)) !== null) {
    const name = match[1];
    const title = match[2];
    const openIdx = match.index + match[0].lastIndexOf('{');
    const closeIdx = findClosingBrace(cleaned, openIdx);
    if (closeIdx === -1) continue;
    const body = cleaned.slice(openIdx + 1, closeIdx);

    // Extract metadata blocks
    const metadata = {};
    const metaRegex = /metadata\s*\{/g;
    const spans = [];
    let metaMatch;
    while ((metaMatch = metaRegex.exec(body)) !== null) {
      const metaOpen = metaMatch.index + metaMatch[0].lastIndexOf('{');
      const metaClose = findClosingBrace(body, metaOpen);
      if (metaClose === -1) break;
      const metaBody = body.slice(metaOpen + 1, metaClose);
      parseKeyValues(metaBody).forEach(({ key, value }) => {
        metadata[key] = value;
      });
      spans.push({ start: metaMatch.index, end: metaClose });
      metaRegex.lastIndex = metaClose + 1;
    }

    // Remove metadata spans to keep only top-level props
    let bodyWithoutMetadata = '';
    let cursor = 0;
    for (const span of spans) {
      bodyWithoutMetadata += body.slice(cursor, span.start);
      cursor = span.end + 1;
    }
    bodyWithoutMetadata += body.slice(cursor);

    const props = {};
    parseKeyValues(bodyWithoutMetadata).forEach(({ key, value }) => {
      props[key] = value;
    });

    components.push({ name, title, props, metadata });
  }

  return components;
};

const buildFlowMatrix = (content) => {
  const cleaned = stripComments(content);
  const relation = /([A-Za-z_][\w-]*)\s*->\s*([A-Za-z_][\w-]*)\s*(?:(?:'([^']*)')|(?:"([^"]*)"))?/g;
  const flows = [];
  const nodes = [];
  const index = new Map();
  const addNode = (name) => {
    if (!index.has(name)) {
      index.set(name, nodes.length);
      nodes.push(name);
    }
  };

  let match;
  while ((match = relation.exec(cleaned)) !== null) {
    const from = match[1];
    const to = match[2];
    const label = match[3] ?? match[4] ?? null;
    flows.push({ from, to, label });
    addNode(from);
    addNode(to);
  }

  const adjacency = nodes.map(() => nodes.map(() => 0));
  const labels = nodes.map(() => nodes.map(() => null));

  flows.forEach(({ from, to, label }) => {
    const i = index.get(from);
    const j = index.get(to);
    if (i !== undefined && j !== undefined) {
      adjacency[i][j] = 1;
      labels[i][j] = label;
    }
  });

  const components = parseComponents(cleaned, true);

  return { nodes, adjacency, labels, flows, components };
};

const send = (res, status, body, headers = {}) => {
  res.writeHead(status, { 'Cache-Control': 'no-store', ...headers });
  res.end(body);
};

const server = createServer(async (req, res) => {
  if (!req.url) return send(res, 400, 'Bad Request');
  const url = req.url.split('?')[0];

  // API: get current C4 file contents
  if (req.method === 'GET' && url === '/c4') {
    const { requested, canonical } = resolveStoragePaths(req);
    const responsePath = canonical || requested;
    const logSuffix = requested !== responsePath ? ` -> ${responsePath}` : '';
    console.log(`LikeC4 load: ${requested}${logSuffix}`);
    try {
      const { content, contentType, missing } = await readLikeC4Content(requested, responsePath);
      const previewFile = await syncPreviewFile(content, responsePath);
      if (missing) {
        return send(
          res,
          200,
          JSON.stringify({ content: '', missing: true, file: responsePath, preview_file: previewFile }),
          { 'Content-Type': MIME['.json'] },
        );
      }
      return send(
        res,
        200,
        JSON.stringify({ content, file: responsePath, content_type: contentType, preview_file: previewFile }),
        { 'Content-Type': MIME['.json'] },
      );
    } catch (err) {
      return send(
        res,
        500,
        JSON.stringify({ error: `Cannot read ${responsePath}: ${err.message}` }),
        { 'Content-Type': MIME['.json'] },
      );
    }
  }

  // API: export current C4 file as downloadable JSON
  if (req.method === 'GET' && url === '/export-json') {
    const { requested, canonical } = resolveStoragePaths(req);
    const responsePath = canonical || requested;
    try {
      const { content, missing, path: usedPath } = await readLikeC4Content(requested, responsePath);
      if (missing) {
        return send(
          res,
          404,
          JSON.stringify({ error: `File not found: ${responsePath}` }),
          { 'Content-Type': MIME['.json'] },
        );
      }
      const exportName = (() => {
        const base = basename(usedPath || responsePath) || 'c4-file';
        return base.toLowerCase().endsWith('.json') ? base : `${base}.json`;
      })();
      const matrix = buildFlowMatrix(content);
      return send(res, 200, JSON.stringify({
        file: responsePath,
        content,
        flows: matrix.flows,
        components: matrix.components,
        matrix: {
          nodes: matrix.nodes,
          adjacency: matrix.adjacency,
          labels: matrix.labels,
        },
      }), {
        'Content-Type': MIME['.json'],
        'Content-Disposition': `attachment; filename="${exportName}"`,
      });
    } catch (err) {
      return send(
        res,
        500,
        JSON.stringify({ error: `Cannot export ${responsePath}: ${err.message}` }),
        { 'Content-Type': MIME['.json'] },
      );
    }
  }

  // API: export flows/matrix only as JSON
  if (req.method === 'GET' && url === '/flow-matrix') {
    const { requested, canonical } = resolveStoragePaths(req);
    const responsePath = canonical || requested;
    try {
      const { content, missing, path: usedPath } = await readLikeC4Content(requested, responsePath);
      if (missing) {
        return send(
          res,
          404,
          JSON.stringify({ error: `File not found: ${responsePath}` }),
          { 'Content-Type': MIME['.json'] },
        );
      }
      const matrix = buildFlowMatrix(content);
      const base = basename(usedPath || responsePath).replace(/\.[^.]+$/, '') || 'c4-file';
      const exportName = `${base}-flows.json`;
      return send(res, 200, JSON.stringify({
        file: responsePath,
        flows: matrix.flows,
        components: matrix.components,
        matrix: {
          nodes: matrix.nodes,
          adjacency: matrix.adjacency,
          labels: matrix.labels,
        },
      }), {
        'Content-Type': MIME['.json'],
        'Content-Disposition': `attachment; filename="${exportName}"`,
      });
    } catch (err) {
      return send(
        res,
        500,
        JSON.stringify({ error: `Cannot export flows from ${responsePath}: ${err.message}` }),
        { 'Content-Type': MIME['.json'] },
      );
    }
  }

  // API: save new contents
  if (req.method === 'POST' && url === '/save') {
    if (!requireApiAuth(req, res)) return;
    const { requested, canonical } = resolveStoragePaths(req);
    const storagePath = canonical || requested;
    if (requested !== storagePath) {
      console.log(`LikeC4 save path remap: ${requested} -> ${storagePath}`);
    }
    console.log(`LikeC4 save start: ${storagePath}`);
    let data = '';
    req.on('data', chunk => {
      data += chunk;
      if (data.length > 5 * 1024 * 1024) {
        req.destroy();
        send(res, 413, 'Payload too large');
      }
    });
    req.on('end', async () => {
      try {
        const payload = JSON.parse(data || '{}');
        const content = payload.content ?? '';
        console.log(`LikeC4 save payload size: ${Buffer.byteLength(content, 'utf8')} bytes`);
        const writeResult = await writeToSeaweed(storagePath, content);
        const previewFile = await syncPreviewFile(content, storagePath);
        await postMetadata({
          filePath: storagePath,
          size: writeResult.size,
          contentType: writeResult.contentType,
        });
        send(
          res,
          200,
          JSON.stringify({
            ok: true,
            file: storagePath,
            size: writeResult.size,
            content_type: writeResult.contentType,
            preview_file: previewFile,
            png_path: null,
          }),
          { 'Content-Type': MIME['.json'] },
        );
      } catch (err) {
        send(res, 400, JSON.stringify({ error: err.message }), { 'Content-Type': MIME['.json'] });
      }
    });
    return;
  }

  // Static UI assets (serve only from /ui)
  let decodedPath = '';
  try {
    decodedPath = decodeURIComponent(url);
  } catch {
    decodedPath = url;
  }
  const requestPath = decodedPath.replace(/^\//, '');
  const filePath = url === '/' ? join(PUBLIC_DIR, 'index.html') : safePublicPath(requestPath);
  if (!filePath) {
    send(res, 404, 'Not Found');
    return;
  }
  try {
    await access(filePath);
    const ext = extname(filePath).toLowerCase();
    res.writeHead(200, {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Cache-Control': 'no-cache',
    });
    createReadStream(filePath).pipe(res);
    return;
  } catch {
    // fallthrough
  }
  send(res, 404, 'Not Found');
});

server.listen(PORT, () => {
  console.log(`Editor server running on http://localhost:${PORT}`);
  console.log(`Default storage path: ${DEFAULT_STORAGE_PATH}`);
});
