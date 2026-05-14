// Cloudflare Worker: parks-proxy
//
// Static-site CORS relay for the /parks app. Forwards GETs to a small
// allowlist of NYC/news hosts and adds Access-Control-Allow-Origin so the
// browser will accept the response. Caches each upstream for 5 minutes at
// the Cloudflare edge.
//
// Deploy:
//   npm i -g wrangler
//   wrangler login
//   mkdir parks-proxy && cd parks-proxy && wrangler init -y
//   # replace src/index.js with this file's contents
//   wrangler deploy
//
// After deploy, copy the *.workers.dev URL into WORKER_URL near the top of
// parks/index.html. Optionally point a custom subdomain at the worker via
// the Cloudflare dashboard.

const ALLOWED_HOSTS = new Set([
  'www.nycgovparks.org',
  'nycgovparks.org',
  'news.google.com',
  'html.duckduckgo.com',
  'duckduckgo.com',
]);

const ALLOWED_ORIGINS = [
  'https://maxgoodstein.com',
  'http://localhost:8092',
  'http://localhost:8080',
  'http://localhost:8081',
];

function corsHeaders(origin) {
  const allow = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    'Access-Control-Allow-Origin': allow,
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Vary': 'Origin',
  };
}

export default {
  async fetch(req) {
    const origin = req.headers.get('Origin') || '';
    if (req.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }
    if (req.method !== 'GET') {
      return new Response('method not allowed', { status: 405, headers: corsHeaders(origin) });
    }

    const u = new URL(req.url);
    const target = u.searchParams.get('url');
    if (!target) {
      return new Response('missing url', { status: 400, headers: corsHeaders(origin) });
    }
    let t;
    try { t = new URL(target); } catch {
      return new Response('bad url', { status: 400, headers: corsHeaders(origin) });
    }
    if (!ALLOWED_HOSTS.has(t.host)) {
      return new Response('host not allowed', { status: 403, headers: corsHeaders(origin) });
    }

    const upstream = await fetch(t.toString(), {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; parks-lookup/1.0; +https://maxgoodstein.com/parks)',
        'Accept': 'text/html,application/xhtml+xml,application/xml,application/rss+xml,*/*',
        'Accept-Language': 'en-US,en;q=0.9',
      },
      cf: { cacheTtl: 300, cacheEverything: true },
    });

    const headers = new Headers(corsHeaders(origin));
    headers.set('Content-Type', upstream.headers.get('content-type') || 'application/octet-stream');
    headers.set('Cache-Control', 'public, max-age=300');
    return new Response(upstream.body, { status: upstream.status, headers });
  },
};
