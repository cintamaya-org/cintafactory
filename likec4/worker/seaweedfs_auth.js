const { createHmac } = require('crypto');

const base64url = (value) => Buffer.from(value).toString('base64url');

const buildFilerJwt = ({ key, path, method, ttlSeconds = 60 }) => {
  if (!key) return '';
  const now = Math.floor(Date.now() / 1000);
  const header = base64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = base64url(JSON.stringify({
    allowed_prefixes: [`/${String(path || '').replace(/^\/+/, '')}`],
    allowed_methods: [String(method || 'GET').toUpperCase()],
    iat: now,
    exp: now + Math.max(1, Number.parseInt(ttlSeconds, 10) || 60),
  }));
  const signingInput = `${header}.${payload}`;
  const signature = createHmac('sha256', key).update(signingInput).digest('base64url');
  return `${signingInput}.${signature}`;
};

const seaweedAuthHeaders = (path, method) => {
  const normalizedMethod = String(method || 'GET').toUpperCase();
  const isWrite = ['PUT', 'POST', 'DELETE'].includes(normalizedMethod);
  const key = isWrite
    ? process.env.SEAWEEDFS_JWT_WRITE_KEY
    : process.env.SEAWEEDFS_JWT_READ_KEY;
  const token = buildFilerJwt({
    key,
    path,
    method: normalizedMethod,
    ttlSeconds: process.env.SEAWEEDFS_JWT_TTL_SECONDS,
  });
  return token ? { Authorization: `Bearer ${token}` } : {};
};

module.exports = { buildFilerJwt, seaweedAuthHeaders };
