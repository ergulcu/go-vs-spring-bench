// Tek bir endpoint'i (ya da karışık yükü) sabit eşzamanlılıkla yükler.
// Ortam değişkenleri: TARGET, ENDPOINT, VUS, DURATION, OUT
import http from 'k6/http';
import exec from 'k6/execution';
import { Trend } from 'k6/metrics';

const BASE = __ENV.TARGET || 'http://bench-go:8080';
const EP = __ENV.ENDPOINT || 'mixed';
const VUS = parseInt(__ENV.VUS || '64');
const DURATION = __ENV.DURATION || '20s';
const STORE = __ENV.STORE || 'postgres';  // postgres | valkey (valkey modunda /stats yok)
const MAX_ID = 100000;          // tohumlanan ürün sayısı
const STORES = 20;              // tohumlanan mağaza sayısı
const DEL_BASE = 10000000;      // silme testi için ayrılmış kimlik aralığı (orkestratör önceden ekler)

http.setResponseCallback(http.expectedStatuses({ min: 200, max: 299 }));

export const options = {
  scenarios: {
    load: { executor: 'constant-vus', vus: VUS, duration: DURATION },
  },
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

const JSON_HDR = { headers: { 'Content-Type': 'application/json' } };
const TEXT_HDR = { headers: { 'Content-Type': 'text/plain' } };
const B64_BODY = 'Bu satir Base64 testi icin tekrar eden bir metindir. '.repeat(40); // ~2 KB
const rnd = (n) => 1 + Math.floor(Math.random() * n);
const hex4 = () => Math.floor(Math.random() * 65536).toString(16).padStart(4, '0');

const eps = {
  health: () => http.get(`${BASE}/health`),
  list: () => http.get(`${BASE}/items?after=${rnd(MAX_ID - 100)}&limit=50`),
  get: () => http.get(`${BASE}/items/${rnd(MAX_ID)}`),
  create: () => http.post(
    `${BASE}/items`,
    JSON.stringify({ name: 'new-' + Math.random().toString(36).slice(2), category: 'cat-new', price_cents: rnd(100000), stock: rnd(500) }),
    JSON_HDR),
  update: () => http.put(
    `${BASE}/items/${rnd(MAX_ID)}`,
    JSON.stringify({ price_cents: rnd(100000), stock: rnd(500000) }),
    JSON_HDR),
  delete: () => http.del(`${BASE}/items/${DEL_BASE + exec.scenario.iterationInTest + 1}`),
  search: () => http.get(`${BASE}/items/search?q=${hex4()}`),
  stats: () => http.get(`${BASE}/stats`),
  order: () => http.post(`${BASE}/orders`, JSON.stringify({ item_id: rnd(MAX_ID), quantity: 1 }), JSON_HDR),
  cpu: () => http.get(`${BASE}/cpu?n=50000`),
  report_store: () => http.get(`${BASE}/stores/${rnd(STORES)}/sales-report`),
  report_all: () => http.get(`${BASE}/reports/sales`),
  // Veritabanısız mantık: ~2 KB'lık gövdeyi Base64'e çevirir; 1000! hesaplar.
  b64: () => http.post(`${BASE}/base64`, `${rnd(MAX_ID)}:${B64_BODY}`, TEXT_HDR),
  fact: () => http.get(`${BASE}/factorial?n=1000`),
};

// Isınma için karışık yük (silme hariç).
const mixAll = [
  ['health', 5], ['list', 20], ['get', 25], ['search', 10], ['stats', 2],
  ['cpu', 5], ['order', 10], ['create', 10], ['update', 10], ['report_store', 2], ['report_all', 1],
  ['b64', 3], ['fact', 2],
];
const mix = mixAll.filter((m) => !(STORE === 'valkey' && m[0] === 'stats'));
const total = mix.reduce((s, m) => s + m[1], 0);
function pick() {
  let r = Math.random() * total;
  for (const [name, w] of mix) {
    if ((r -= w) < 0) return name;
  }
  return 'get';
}

// Sunucunun kendi ölçtüğü süreler (Server-Timing: data;dur=…, total;dur=…; ms):
//   data  = veri deposunu beklerken geçen süre, total = işleyiciye girişten yanıtın başlamasına kadar.
const srvData = new Trend('srv_data_ms');
const srvTotal = new Trend('srv_total_ms');
const ST = /data;dur=([0-9.]+),[ ]*total;dur=([0-9.]+)/;

export default function () {
  const name = EP === 'mixed' ? pick() : EP;
  const res = eps[name]();
  const h = res.headers['Server-Timing'];
  if (h) {
    const m = ST.exec(h);
    if (m) {
      srvData.add(parseFloat(m[1]));
      srvTotal.add(parseFloat(m[2]));
    }
  }
}

export function handleSummary(data) {
  const out = __ENV.OUT || 'last';
  const dir = __ENV.RESULTS_DIR || '/results';
  return { [`${dir}/${out}.json`]: JSON.stringify(data) };
}
