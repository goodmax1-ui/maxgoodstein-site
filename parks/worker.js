// Cloudflare Worker: parks-proxy
//
// Static-site CORS relay for the /parks app. Two modes:
//   1) Default: GET /?url=<encoded url> proxies an HTML/JSON response from
//      an allowlisted upstream (NYC Parks, DuckDuckGo, etc).
//   2) mode=powerbi: GET /?mode=powerbi&fmsid=<id> queries the NYC Parks
//      Capital Project Tracker Power BI public report and returns clean
//      JSON with the project's specific budget figures.
//
// Deploy:
//   npm i -g wrangler && wrangler login && wrangler deploy
//
// After deploy, copy the *.workers.dev URL into WORKER_URL near the top of
// parks/index.html.

const ALLOWED_HOSTS = new Set([
  'www.nycgovparks.org',
  'nycgovparks.org',
  'news.google.com',
  'html.duckduckgo.com',
  'duckduckgo.com',
]);

// Power BI public-report query endpoint for NYC's Capital Project Tracker.
// Recon: 2026-05-14, captured from app.powerbigov.us/view?r=... in DevTools.
// If NYC rotates the dashboard or any of these IDs, the recon must be repeated.
const POWERBI = {
  endpoint: 'https://wabi-us-gov-virginia-api.analysis.usgovcloudapi.net/public/reports/querydata?synchronous=true',
  resourceKey: '190ac24a-03bd-4968-98b1-c2438e90739e',
  datasetId: 'd7c204a3-b9d0-460c-9c9e-ad4c3484505f',
  reportId: 'a2064d24-eef1-40c7-98b4-ddec7d824b58',
  visualId: '4fe44b9770666a63921e',
  modelId: 968771,
};

const POWERBI_FIELD_MAP = {
  'bi_FMS_Project_List.Managing_Agency_FMS': 'managingAgency',
  'bi_FMS_Project_List.FMSID': 'fmsid',
  'bi_FMS_Project_List.Commitments Total': 'totalBudget',
  'bi_FMS_Project_List.Actual Exp Total': 'spendToDate',
  'bi_FMS_Project_List.Expense to Date': 'spendPercent',
  'bi_FMS_Project_List.Project Name': 'projectName',
  'bi_FMS_Project_List.Agency Project Name': 'agencyProjectName',
  'bi_FMS_Project_List.Client Agency': 'sponsorAgency',
  'bi_FMS_Project_List.Current Phase and NoSchedule Category': 'currentPhase',
  'bi_FMS_Project_List.PID': 'pid',
  'bi_FMS_Project_List.bi_key_ManagingAgencyFMS': 'biKey',
  'Min(bi_FMS_Project_List.Current Phase Start)': 'currentPhaseStart',
  'Min(bi_FMS_Project_List.Current Phase End Forecast)': 'currentPhaseEndForecast',
  'Min(bi_FMS_Project_List.Completion Date Forecast)': 'completionDateForecast',
  'Min(bi_FMS_Project_List.Current Phase)': 'currentPhaseMin',
};

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

function buildPowerBIQuery(fmsid) {
  const safe = fmsid.replace(/'/g, '');
  return {
    version: '1.0.0',
    queries: [{
      Query: {
        Commands: [{
          SemanticQueryDataShapeCommand: {
            Query: {
              Version: 2,
              From: [{ Name: 'b', Entity: 'bi_FMS_Project_List', Type: 0 }],
              Select: [
                { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'Managing_Agency_FMS' }, Name: 'bi_FMS_Project_List.Managing_Agency_FMS' },
                { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'FMSID' }, Name: 'bi_FMS_Project_List.FMSID' },
                { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'Commitments Total' }, Name: 'bi_FMS_Project_List.Commitments Total' },
                { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'Actual Exp Total' }, Name: 'bi_FMS_Project_List.Actual Exp Total' },
                { Aggregation: { Expression: { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'Expense to Date' } }, Function: 1 }, Name: 'bi_FMS_Project_List.Expense to Date' },
                { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'Project Name' }, Name: 'bi_FMS_Project_List.Project Name' },
                { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'Agency Project Name' }, Name: 'bi_FMS_Project_List.Agency Project Name' },
                { Aggregation: { Expression: { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'Current Phase Start' } }, Function: 3 }, Name: 'Min(bi_FMS_Project_List.Current Phase Start)' },
                { Aggregation: { Expression: { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'Current Phase End Forecast' } }, Function: 3 }, Name: 'Min(bi_FMS_Project_List.Current Phase End Forecast)' },
                { Aggregation: { Expression: { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'Completion Date Forecast' } }, Function: 3 }, Name: 'Min(bi_FMS_Project_List.Completion Date Forecast)' },
                { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'Client Agency' }, Name: 'bi_FMS_Project_List.Client Agency' },
                { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'Current Phase and NoSchedule Category' }, Name: 'bi_FMS_Project_List.Current Phase and NoSchedule Category' },
                { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'PID' }, Name: 'bi_FMS_Project_List.PID' },
                { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'bi_key_ManagingAgencyFMS' }, Name: 'bi_FMS_Project_List.bi_key_ManagingAgencyFMS' },
                { Aggregation: { Expression: { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'Current Phase' } }, Function: 3 }, Name: 'Min(bi_FMS_Project_List.Current Phase)' },
              ],
              Where: [
                { Condition: { Contains: { Left: { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'Project and FMSID search' } }, Right: { Literal: { Value: `'${safe}'` } } } } },
              ],
              OrderBy: [
                { Direction: 2, Expression: { Column: { Expression: { SourceRef: { Source: 'b' } }, Property: 'Commitments Total' } } },
              ],
            },
            Binding: {
              Primary: { Groupings: [{ Projections: [0, 10, 1, 2, 3, 4, 5, 6, 11, 7, 8, 9, 12, 13, 14] }] },
              DataReduction: { DataVolume: 3, Primary: { Window: { Count: 10 } } },
              Version: 1,
            },
            ExecutionMetricsKind: 1,
          },
        }],
      },
      QueryId: '',
      ApplicationContext: {
        DatasetId: POWERBI.datasetId,
        Sources: [{ ReportId: POWERBI.reportId, VisualId: POWERBI.visualId }],
      },
    }],
    cancelQueries: [],
    modelId: POWERBI.modelId,
  };
}

function parsePowerBIRow(json) {
  const data = json?.results?.[0]?.result?.data;
  if (!data) return null;
  const ds = data.dsr?.DS?.[0];
  const row = ds?.PH?.[0]?.DM0?.[0];
  if (!row) return null;
  const valueDicts = ds.ValueDicts || {};
  const schema = row.S || [];
  const cells = row.C || [];

  const selectMap = {};
  for (const sel of data.descriptor?.Select || []) {
    selectMap[sel.Value] = POWERBI_FIELD_MAP[sel.Name] || sel.Name;
  }

  const out = {};
  for (let i = 0; i < schema.length; i++) {
    const col = schema[i];
    const raw = cells[i];
    const name = selectMap[col.N] || col.N;
    if (raw === null || raw === undefined) { out[name] = null; continue; }
    if (col.T === 1 && col.DN) {
      out[name] = valueDicts[col.DN]?.[raw] ?? null;
    } else if (col.T === 7) {
      out[name] = typeof raw === 'number' ? new Date(raw).toISOString() : null;
    } else {
      out[name] = raw;
    }
  }
  return out;
}

async function handlePowerBI(origin, fmsid) {
  const jsonHeaders = { ...corsHeaders(origin), 'Content-Type': 'application/json' };
  if (!fmsid || !/^[A-Za-z0-9 -]{3,40}$/.test(fmsid)) {
    return new Response(JSON.stringify({ error: 'invalid fmsid' }), { status: 400, headers: jsonHeaders });
  }
  const body = buildPowerBIQuery(fmsid);
  let upstream;
  try {
    upstream = await fetch(POWERBI.endpoint, {
      method: 'POST',
      headers: {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json;charset=UTF-8',
        'Origin': 'https://app.powerbigov.us',
        'Referer': 'https://app.powerbigov.us/',
        'X-Powerbi-Resourcekey': POWERBI.resourceKey,
        'Activityid': crypto.randomUUID(),
        'Requestid': crypto.randomUUID(),
        'User-Agent': 'Mozilla/5.0 (compatible; parks-lookup/1.0; +https://maxgoodstein.com/parks)',
      },
      body: JSON.stringify(body),
      cf: { cacheTtl: 3600, cacheEverything: true },
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: 'fetch failed', detail: String(e) }), { status: 502, headers: jsonHeaders });
  }
  if (!upstream.ok) {
    return new Response(JSON.stringify({ error: 'upstream failed', status: upstream.status }), { status: 502, headers: jsonHeaders });
  }
  let json;
  try { json = await upstream.json(); } catch (e) {
    return new Response(JSON.stringify({ error: 'parse failed' }), { status: 502, headers: jsonHeaders });
  }
  const parsed = parsePowerBIRow(json);
  return new Response(JSON.stringify(parsed || { error: 'no row' }), {
    status: 200,
    headers: { ...jsonHeaders, 'Cache-Control': 'public, max-age=3600' },
  });
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
    const mode = u.searchParams.get('mode');
    if (mode === 'powerbi') {
      return handlePowerBI(origin, u.searchParams.get('fmsid'));
    }

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
