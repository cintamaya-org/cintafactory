const http = require('http');
const { mkdir, readFile, readdir, rm, writeFile } = require('fs').promises;
const { createHash } = require('crypto');
const { dirname, join, posix, relative, sep } = require('path');
const { spawn } = require('child_process');
const { URL } = require('url');

const EXPORT_HOST = process.env.LIKEC4_EXPORT_HOST || '0.0.0.0';
const EXPORT_PORT = Number.parseInt(process.env.LIKEC4_EXPORT_PORT || '9000', 10);
const MAX_BODY_BYTES = Number.parseInt(process.env.LIKEC4_EXPORT_MAX_BODY_BYTES || '1048576', 10);
const SEAWEEDFS_FILER_URL = (process.env.SEAWEEDFS_FILER_URL || '').replace(/\/+$/, '');
const SEAWEEDFS_BASE_DIR = (process.env.SEAWEEDFS_BASE_DIR || '').replace(/^\/+|\/+$/g, '');
const LIKEC4_METADATA_URL = process.env.LIKEC4_METADATA_URL || '';
const LIKEC4_METADATA_TOKEN = process.env.LIKEC4_METADATA_TOKEN || 'dev_token_idHaf';
const EXPORT_ROOT = process.env.LIKEC4_EXPORT_TMP || '/tmp/likec4-export';
const LOCAL_EXPORT_DIR = (process.env.LIKEC4_EXPORT_LOCAL_DIR || '/var/likec4-exports').replace(/\/+$/, '');
const EXPORT_FORMAT = process.env.LIKEC4_EXPORT_FORMAT || 'png';
const EXPORT_VIEW = process.env.LIKEC4_EXPORT_VIEW || '';
const MAX_RETRIES = Number.parseInt(process.env.LIKEC4_EXPORT_MAX_RETRIES || '3', 10);
const parseBool = (value, defaultValue = true) => {
  if (value === undefined || value === null || value === '') {
    return defaultValue;
  }
  const normalized = String(value).trim().toLowerCase();
  if (['0', 'false', 'no', 'off'].includes(normalized)) {
    return false;
  }
  if (['1', 'true', 'yes', 'on'].includes(normalized)) {
    return true;
  }
  return defaultValue;
};

const DELETE_OLD_EXPORTS = parseBool(process.env.LIKEC4_EXPORT_DELETE_OLD, true);

const encodeSeaweedPath = (path) => {
  const clean = String(path || '').replace(/^\/+/, '');
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
    throw new Error(`SeaweedFS file not found: ${path}`);
  }
  if (!response.ok) {
    throw new Error(`SeaweedFS read failed (${response.status})`);
  }
  return response.text();
};

const headFromSeaweed = async (path) => {
  const url = buildSeaweedUrl(path);
  const response = await fetch(url, { method: 'HEAD' });
  if (response.status === 404) {
    throw new Error(`SeaweedFS file not found: ${path}`);
  }
  if (!response.ok) {
    throw new Error(`SeaweedFS head failed (${response.status})`);
  }
  const length = response.headers.get('content-length') || '0';
  const contentType = response.headers.get('content-type') || 'text/plain';
  const size = Number.parseInt(length, 10);
  return { size: Number.isFinite(size) ? size : 0, contentType };
};

const writeToSeaweed = async (path, buffer, contentType) => {
  const url = buildSeaweedUrl(path);
  const response = await fetch(url, {
    method: 'PUT',
    headers: {
      'Content-Type': contentType,
      'Content-Length': String(buffer.length),
    },
    body: buffer,
  });
  if (!response.ok) {
    throw new Error(`SeaweedFS write failed (${response.status})`);
  }
};

const likec4PngPathFor = (storagePath) => {
  const cleaned = String(storagePath || '').replace(/^\/+/, '');
  const parts = cleaned.split('/').filter(Boolean);
  if (parts.length >= 3 && parts[0] === 'diagrams') {
    return `diagrams/${parts[1]}/views/thumb.png`;
  }
  const baseName = posix.basename(cleaned || 'diagram.c4');
  const base = baseName.toLowerCase().endsWith('.c4') ? baseName.slice(0, -3) : baseName;
  return `diagrams/likec4/${base}/views/thumb.png`;
};

const likec4ViewsDirFor = (storagePath) => {
  const cleaned = String(storagePath || '').replace(/^\/+/, '');
  const parts = cleaned.split('/').filter(Boolean);
  if (parts.length >= 3 && parts[0] === 'diagrams') {
    return `diagrams/${parts[1]}/views`;
  }
  const baseName = posix.basename(cleaned || 'diagram.c4');
  const base = baseName.toLowerCase().endsWith('.c4') ? baseName.slice(0, -3) : baseName;
  return `diagrams/likec4/${base}/views`;
};

const safeLocalJoin = (baseDir, relativePath) => {
  const cleaned = String(relativePath || '').replace(/^\/+/, '');
  if (!cleaned) return '';
  const normalized = posix.normalize(cleaned);
  if (!normalized || normalized.startsWith('..') || normalized.includes('/..')) {
    return '';
  }
  return join(baseDir, normalized);
};

const normalizeRelativePath = (baseDir, filePath) => {
  const rel = relative(baseDir, filePath);
  const posixRel = posix.normalize(rel.split(sep).join('/'));
  if (!posixRel || posixRel === '.' || posixRel.startsWith('..') || posixRel.includes('/..')) {
    return '';
  }
  return posixRel;
};

const runCommand = (cmd, args, cwd) => new Promise((resolve, reject) => {
  console.log(`LikeC4 export: run command: ${cmd} ${args.join(' ')} (cwd=${cwd})`);
  const child = spawn(cmd, args, { cwd, stdio: ['ignore', 'pipe', 'pipe'] });
  console.log(`LikeC4 export: 1`);
  let stdout = '';
  let stderr = '';
  console.log(`LikeC4 export:2`);
  child.stdout.on('data', chunk => {
    stdout += chunk.toString();
  });
  console.log(`LikeC4 export: 3`);
  child.stderr.on('data', chunk => {
    stderr += chunk.toString();
  });
  console.log(`LikeC4 export: 4`);
  child.on('error', reject);
  console.log(`LikeC4 export: 5`);
  child.on('close', code => {
    if (code === 0) {
      if (stdout.trim()) {
        console.log(`LikeC4 export: command stdout: ${stdout.trim()}`);
      }
      if (stderr.trim()) {
        console.warn(`LikeC4 export: command stderr: ${stderr.trim()}`);
      }
      console.log(`LikeC4 export: 666`);
      console.log(`LikeC4 export: CODE : ${code}`);
      console.log(`LikeC4 export:  stdout: ${String(stdout)}`);
      console.log(`LikeC4 export: 777`);
      resolve({ stdout, stderr });
    } else {
      reject(new Error(`Command failed (${code}): ${cmd} ${args.join(' ')}\n${stderr}`));
    }
  });
});

const findPngFiles = async (dir, depth = 0, maxDepth = 4) => {
  if (depth > maxDepth) return [];
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  const results = [];
  for (const entry of entries) {
    const fullPath = join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...await findPngFiles(fullPath, depth + 1, maxDepth));
    } else if (entry.isFile() && entry.name.toLowerCase().endsWith('.png')) {
      results.push(fullPath);
    }
  }
  return results;
};

const selectPng = (paths) => {
  if (!paths.length) return null;
  if (EXPORT_VIEW) {
    const preferred = paths.find(path => path.toLowerCase().includes(EXPORT_VIEW.toLowerCase()));
    if (preferred) return preferred;
  }
  return paths.sort()[0];
};

const exportLikeC4 = async (inputPath, workDir) => {
  const outputDir = join(workDir, 'out');
  console.log(`LikeC4 export: preparing output dir ${outputDir}`);
  await mkdir(outputDir, { recursive: true });
  const viewArgs = EXPORT_VIEW ? ['--filter', EXPORT_VIEW] : [];
  const formatToken = EXPORT_FORMAT || 'png';
  const sourceArg = '.';
  const candidates = [
    ['export', formatToken, '-o', outputDir, sourceArg, ...viewArgs],
    ['export', formatToken, '-o', outputDir, ...viewArgs, sourceArg],
  ];
  let lastError = null;
  for (const args of candidates) {
    try {
      console.log(`LikeC4 export: trying likec4 ${args.join(' ')}`);
      await runCommand('likec4', args, workDir);
      const pngs = [
        ...await findPngFiles(outputDir),
        ...await findPngFiles(workDir),
      ];
      console.log(`LikeC4 export: found PNGs: ${pngs.length ? pngs.join(', ') : 'none'}`);
      const uniquePngs = Array.from(new Set(pngs));
      const selected = selectPng(uniquePngs) || uniquePngs[0] || null;
      if (selected) {
        console.log(`LikeC4 export: selected PNG ${selected}`);
        return { pngs: uniquePngs, selected, outputDir };
      }
      lastError = new Error(`No PNG output detected after: likec4 ${args.join(' ')}`);
    } catch (err) {
      console.warn(`LikeC4 export: command failed: ${err.message}`);
      lastError = err;
    }
  }
  throw lastError || new Error('LikeC4 export failed');
};

const postMetadata = async ({ filePath, size, contentType, pngPath, pngSize, pngContentType, pngPaths }) => {
  if (!LIKEC4_METADATA_URL) {
    console.warn('LIKEC4_METADATA_URL not configured; skipping metadata update.');
    return;
  }
  const headers = { 'Content-Type': 'application/json' };
  const url = LIKEC4_METADATA_URL;
  const payload = {
    path: filePath,
    size,
    content_type: contentType,
    png_path: pngPath,
    png_size: pngSize,
    png_content_type: pngContentType,
  };
  if (LIKEC4_METADATA_TOKEN) {
    headers['X-LikeC4-Token'] = LIKEC4_METADATA_TOKEN;
    payload.token = LIKEC4_METADATA_TOKEN;
  }
  if (Array.isArray(pngPaths) && pngPaths.length) {
    payload.png_paths = pngPaths;
  }
  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`Metadata update failed (${response.status}) ${body}`);
  }
};

const processJob = async (payload) => {
  const storagePath = String(payload.storage_path || '').trim();
  if (!storagePath) {
    throw new Error('Missing storage_path');
  }
  console.log(`Export start: ${storagePath}`);
  console.log('LikeC4 export: reading source from SeaweedFS');
  const content = await readFromSeaweed(storagePath);
  console.log('LikeC4 export: reading metadata from SeaweedFS');
  const { size, contentType } = await headFromSeaweed(storagePath);
  const jobId = createHash('sha1').update(`${storagePath}-${Date.now()}`).digest('hex').slice(0, 12);
  const workDir = join(EXPORT_ROOT, jobId);
  const inputPath = join(workDir, 'diagram.c4');
  console.log(`LikeC4 export: creating work dir ${workDir}`);
  await mkdir(workDir, { recursive: true });
  try {
    console.log(`LikeC4 export: writing input file ${inputPath}`);
    await writeFile(inputPath, content ?? '', 'utf8');
    console.log('LikeC4 export: running likec4 CLI');
    const exportResult = await exportLikeC4(inputPath, workDir);
    const pngFiles = exportResult.pngs || [];
    const selected = exportResult.selected || pngFiles[0] || null;
    const outputDir = exportResult.outputDir || workDir;
    const primaryPngPath = likec4PngPathFor(storagePath);
    const viewsBaseDir = likec4ViewsDirFor(storagePath);
    let existingLocalPngs = [];
    if (LOCAL_EXPORT_DIR && DELETE_OLD_EXPORTS) {
      const localViewsDir = safeLocalJoin(LOCAL_EXPORT_DIR, viewsBaseDir);
      if (!localViewsDir) {
        throw new Error(`Invalid local export path for ${viewsBaseDir}`);
      }
      existingLocalPngs = await findPngFiles(localViewsDir);
    }
    if (LOCAL_EXPORT_DIR) {
      const localC4Path = safeLocalJoin(LOCAL_EXPORT_DIR, storagePath);
      if (!localC4Path) {
        throw new Error(`Invalid local export path for ${storagePath}`);
      }
      console.log(`LikeC4 export: writing local .c4 ${localC4Path}`);
      await mkdir(dirname(localC4Path), { recursive: true });
      await writeFile(localC4Path, content ?? '', 'utf8');
    }
    if (!pngFiles.length) {
      throw new Error('LikeC4 export produced no PNG files.');
    }
    let primaryBuffer = null;
    const uploadedPaths = [];
    const viewPaths = [];
    const newLocalPngs = new Set();
    for (const pngFile of pngFiles) {
      const isPrimary = selected && pngFile === selected;
      console.log(`LikeC4 export: reading PNG file ${pngFile}`);
      const pngBuffer = await readFile(pngFile);
      const relativePng = normalizeRelativePath(outputDir, pngFile);
      const viewSuffix = relativePng || posix.basename(pngFile);
      const viewTargetPath = `${viewsBaseDir}/${viewSuffix}`;
      if (LOCAL_EXPORT_DIR) {
        const localPngPath = safeLocalJoin(LOCAL_EXPORT_DIR, viewTargetPath);
        if (!localPngPath) {
          throw new Error(`Invalid local export path for ${viewTargetPath}`);
        }
        console.log(`LikeC4 export: writing local PNG ${localPngPath}`);
        await mkdir(dirname(localPngPath), { recursive: true });
        await writeFile(localPngPath, pngBuffer);
        newLocalPngs.add(localPngPath);
      }
      console.log(`LikeC4 export: uploading PNG to SeaweedFS ${viewTargetPath}`);
      await writeToSeaweed(viewTargetPath, pngBuffer, 'image/png');
      uploadedPaths.push(viewTargetPath);
      viewPaths.push(viewTargetPath);
      if (isPrimary) {
        primaryBuffer = pngBuffer;
        if (primaryPngPath !== viewTargetPath) {
          if (LOCAL_EXPORT_DIR) {
            const localPrimaryPath = safeLocalJoin(LOCAL_EXPORT_DIR, primaryPngPath);
            if (!localPrimaryPath) {
              throw new Error(`Invalid local export path for ${primaryPngPath}`);
            }
            console.log(`LikeC4 export: writing local PNG ${localPrimaryPath}`);
            await mkdir(dirname(localPrimaryPath), { recursive: true });
            await writeFile(localPrimaryPath, pngBuffer);
            newLocalPngs.add(localPrimaryPath);
          }
          console.log(`LikeC4 export: uploading PNG to SeaweedFS ${primaryPngPath}`);
          await writeToSeaweed(primaryPngPath, pngBuffer, 'image/png');
          uploadedPaths.push(primaryPngPath);
        }
      }
    }
    if (!primaryBuffer) {
      primaryBuffer = await readFile(selected || pngFiles[0]);
    }
    const uniqueUploadedPaths = Array.from(new Set(uploadedPaths));
    const uniqueViewPaths = Array.from(new Set(viewPaths));
    console.log('LikeC4 export: posting metadata');
    await postMetadata({
      filePath: storagePath,
      size,
      contentType,
      pngPath: primaryPngPath,
      pngSize: primaryBuffer.length,
      pngContentType: 'image/png',
      pngPaths: uniqueViewPaths,
    });
    if (LOCAL_EXPORT_DIR && DELETE_OLD_EXPORTS && existingLocalPngs.length) {
      const toDelete = existingLocalPngs.filter(path => !newLocalPngs.has(path));
      for (const oldPath of toDelete) {
        try {
          await rm(oldPath, { force: true });
        } catch (err) {
          console.warn(`LikeC4 export: failed to delete local PNG ${oldPath}: ${err.message}`);
        }
      }
    }
    console.log(`Export done: ${storagePath} -> ${primaryPngPath} (+${uniqueViewPaths.length} view PNGs)`);
    return {
      storage_path: storagePath,
      png_path: primaryPngPath,
      png_size: primaryBuffer.length,
      png_content_type: 'image/png',
      png_paths: uniqueViewPaths,
    };
  } finally {
    try {
      await rm(workDir, { recursive: true, force: true });
    } catch {
      // ignore cleanup errors
    }
  }
};

const readBody = (req) => new Promise((resolve, reject) => {
  let size = 0;
  const chunks = [];
  req.on('data', (chunk) => {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) {
      reject(new Error('Payload too large'));
      req.destroy();
      return;
    }
    chunks.push(chunk);
  });
  req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
  req.on('error', reject);
});

const readJsonBody = async (req) => {
  const raw = await readBody(req);
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch {
    throw new Error('Invalid JSON payload');
  }
};

const sendJson = (res, status, payload) => {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(body),
  });
  res.end(body);
};

const runExportWithRetries = async (payload) => {
  const attempts = Math.max(0, Number.isFinite(MAX_RETRIES) ? MAX_RETRIES : 0) + 1;
  let lastError = null;
  for (let idx = 1; idx <= attempts; idx += 1) {
    try {
      return await processJob(payload);
    } catch (err) {
      lastError = err;
      console.error(`Export failed (attempt ${idx}/${attempts}): ${err.message}`);
    }
  }
  throw lastError || new Error('LikeC4 export failed');
};

const start = async () => {
  if (!SEAWEEDFS_FILER_URL) {
    console.error('SEAWEEDFS_FILER_URL must be configured.');
    process.exit(1);
  }
  const server = http.createServer(async (req, res) => {
    let pathname = '/';
    try {
      pathname = new URL(req.url, `http://${req.headers.host || 'localhost'}`).pathname;
    } catch {
      pathname = req.url || '/';
    }
    if (req.method === 'GET' && pathname === '/health') {
      sendJson(res, 200, { ok: true });
      return;
    }
    if (req.method !== 'POST' || pathname !== '/export') {
      res.statusCode = 404;
      res.end();
      return;
    }
    let payload = null;
    try {
      payload = await readJsonBody(req);
    } catch (err) {
      const status = err.message === 'Payload too large' ? 413 : 400;
      sendJson(res, status, { ok: false, error: err.message });
      return;
    }
    const storagePath = String(payload?.storage_path || '').trim();
    if (!storagePath) {
      sendJson(res, 400, { ok: false, error: 'Missing storage_path' });
      return;
    }
    try {
      const result = await runExportWithRetries({ ...payload, storage_path: storagePath });
      sendJson(res, 200, { ok: true, ...result });
    } catch (err) {
      sendJson(res, 500, { ok: false, error: err.message });
    }
  });
  server.listen(EXPORT_PORT, EXPORT_HOST, () => {
    console.log(`LikeC4 exporter listening on ${EXPORT_HOST}:${EXPORT_PORT}`);
  });
};

start().catch((err) => {
  console.error('Exporter crashed:', err);
  process.exit(1);
});
