// Cloudflare Worker: cut-tracker-vault
//
// Stores ONE encrypted vault blob and serves it back. Treats the blob as
// opaque — the AES-GCM ciphertext is generated client-side with the user's
// passphrase, so the Worker never sees plaintext. Bearer auth gates the
// endpoint against junk traffic; the real secrecy is the passphrase.
//
// Endpoints:
//   GET  /vault             → { v, salt, iv, ct, updatedAt } | 404
//   PUT  /vault             → body is the same shape, writes it
//   GET  /pending-cron      → [{ date, nutrients, postedAt }, ...]
//   PUT  /pending-cron      → push one parsed-Cronometer day (server-side scraper)
//   DELETE /pending-cron    → ?date=YYYY-MM-DD removes a consumed entry
//   GET  /healthz           → "ok"
//
// /pending-cron holds plaintext nutrient totals — NOT identifying info. The
// client merges + encrypts on next unlock, then DELETEs the entry. The
// passphrase never touches this endpoint. Same bearer token gates writes.
//
// Deploy:
//   wrangler kv namespace create HEALTH_KV
//   # paste the returned id into wrangler.toml
//   wrangler secret put AUTH_TOKEN     # any long random string
//   wrangler deploy
//
// Client config (in /health page settings):
//   Worker URL    = https://<your-worker>.workers.dev
//   Auth token    = the AUTH_TOKEN secret

const VAULT_KEY = 'vault:default';
const PENDING_PREFIX = 'pending-cron:'; // pending-cron:YYYY-MM-DD
const MAX_BYTES = 256 * 1024; // 256 KB ceiling per write
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

const ALLOWED_ORIGINS = [
  'https://maxgoodstein.com',
  'http://localhost:8081',
  'http://localhost:8080',
  'http://localhost:8092',
];

function corsHeaders(origin) {
  const allow = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    'Access-Control-Allow-Origin': allow,
    'Access-Control-Allow-Methods': 'GET, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Authorization, Content-Type, If-Match',
    'Access-Control-Expose-Headers': 'ETag',
    'Vary': 'Origin',
  };
}

function json(origin, status, body, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(origin), 'Content-Type': 'application/json', ...extra },
  });
}

function isAuthorized(req, env) {
  const h = req.headers.get('Authorization') || '';
  const token = h.startsWith('Bearer ') ? h.slice(7) : '';
  if (!token || !env.AUTH_TOKEN) return false;
  // constant-time compare
  if (token.length !== env.AUTH_TOKEN.length) return false;
  let diff = 0;
  for (let i = 0; i < token.length; i++) diff |= token.charCodeAt(i) ^ env.AUTH_TOKEN.charCodeAt(i);
  return diff === 0;
}

function isValidWrap(obj) {
  return obj
    && typeof obj === 'object'
    && obj.v === 1
    && typeof obj.salt === 'string'
    && typeof obj.iv === 'string'
    && typeof obj.ct === 'string'
    && obj.salt.length < 64
    && obj.iv.length < 64
    && obj.ct.length < MAX_BYTES;
}

export default {
  async fetch(req, env) {
    const origin = req.headers.get('Origin') || '';
    const u = new URL(req.url);

    if (req.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }

    if (u.pathname === '/healthz') {
      return new Response('ok', { status: 200, headers: corsHeaders(origin) });
    }

    if (!isAuthorized(req, env)) {
      return json(origin, 401, { error: 'unauthorized' });
    }

    if (u.pathname === '/vault' && req.method === 'GET') {
      const stored = await env.HEALTH_KV.get(VAULT_KEY, { type: 'json' });
      if (!stored) return json(origin, 404, { error: 'no vault' });
      return json(origin, 200, stored);
    }

    if (u.pathname === '/vault' && req.method === 'PUT') {
      let body;
      try { body = await req.json(); }
      catch { return json(origin, 400, { error: 'invalid json' }); }
      if (!isValidWrap(body)) return json(origin, 400, { error: 'invalid vault shape' });
      const payload = { ...body, updatedAt: Date.now() };
      await env.HEALTH_KV.put(VAULT_KEY, JSON.stringify(payload));
      return json(origin, 200, { ok: true, updatedAt: payload.updatedAt });
    }

    if (u.pathname === '/pending-cron' && req.method === 'GET') {
      const list = await env.HEALTH_KV.list({ prefix: PENDING_PREFIX });
      const out = [];
      for (const k of list.keys) {
        const v = await env.HEALTH_KV.get(k.name, { type: 'json' });
        if (v) out.push(v);
      }
      return json(origin, 200, out);
    }

    if (u.pathname === '/pending-cron' && req.method === 'PUT') {
      let body;
      try { body = await req.json(); }
      catch { return json(origin, 400, { error: 'invalid json' }); }
      if (!body || !ISO_DATE.test(body.date) || !body.nutrients || typeof body.nutrients !== 'object') {
        return json(origin, 400, { error: 'shape: { date: YYYY-MM-DD, nutrients: {...} }' });
      }
      const entry = { date: body.date, nutrients: body.nutrients, postedAt: Date.now() };
      // 14-day TTL so abandoned entries self-clean
      await env.HEALTH_KV.put(PENDING_PREFIX + body.date, JSON.stringify(entry), { expirationTtl: 60 * 60 * 24 * 14 });
      return json(origin, 200, { ok: true, date: body.date });
    }

    if (u.pathname === '/pending-cron' && req.method === 'DELETE') {
      const date = u.searchParams.get('date');
      if (!date || !ISO_DATE.test(date)) return json(origin, 400, { error: 'date=YYYY-MM-DD required' });
      await env.HEALTH_KV.delete(PENDING_PREFIX + date);
      return json(origin, 200, { ok: true, date });
    }

    return json(origin, 404, { error: 'not found' });
  },
};
