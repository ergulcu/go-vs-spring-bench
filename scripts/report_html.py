#!/usr/bin/env python3
"""results/ altındaki ölçümlerden tek dosyalık, bağımsız bir HTML rapor üretir: results/report.html
Önce report.py'nin çıktısını (summary.json + SVG grafikler) yeniler, sonra HTML'e gömer."""
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report as base  # noqa: E402

ROOT = base.ROOT
OUT = base.OUT
PHASES, LABELS, NAMES = base.PHASES, base.LABELS, base.NAMES

# Elle yazılan yorum ve yöntem notları rapora yalnızca ölçüm klasöründe yorum.html / yontem_notlari.html varsa eklenir
# Kendi koşunuzun yorumunu bu dosya adlarıyla senaryo klasörüne ekleyebilirsiniz.
STORE_NAME = "PostgreSQL"  # main() senaryodan günceller
SINIRLILIK = [
    "Tek makine, tek koşu ortamı: sonuçlar bu makinenin işlemcisine, ısı/güç durumuna ve arka plan yüküne bağlıdır. Bu yüzden birden çok tur, dönüşümlü sırayla (Go→Spring, Spring→Go) koşulur; tur aralığı geniş çıkıyorsa makine sakin değildir.",
    "Docker Desktop (Windows/macOS) bir sanal makine içinde çalışır; ağ ve disk gecikmesi ekler. Çıplak Linux'ta mutlak sayılar farklı olur. Karşılaştırma oranları, mutlak değerlerden daha güvenilirdir.",
    "Yük üreteci (k6), veri deposu (PostgreSQL ya da Valkey) ve uygulamalar aynı makinede çalışır. CPU limitleri uygulamaya (senaryoya göre) ve veri deposuna (varsayılan 8) konur; k6 sınırsızdır. Makinenin çekirdeği azsa konteynerler birbirini etkiler.",
    "Yük kapalı döngüdür (sabit 64 eşzamanlı kullanıcı, bekleme yok): sistem sürekli doygunluğa itilir. Gerçek trafik genelde açık döngüdür; doygunluk altındaki gecikmeler gerçek hayattan yüksektir.",
    "Her endpoint kısa süre ölçülür (varsayılan 20 sn); CPU/RAM örnekleri saniyede ~1 kez alınır (docker stats). Çok kısa tepe değerleri kaçabilir.",
    "Kod en basit, idiomatik haliyle yazıldı (Go: standart kütüphane + pgx ya da go-redis; Spring: MVC + JdbcClient + Hikari ya da Jedis). JIT ayarı, GC ayarı, sanal iş parçacığı, native image (GraalVM) ya da Go'da GOGC/GOMEMLIMIT ayarı denenmedi; bunlar sonuçları değiştirebilir.",
    "Bu bir CRUD API testidir. Uzun süre çalışan sistemlerde bellek sızıntısı, GC davranışı, ekip üretkenliği, kütüphane ekosistemi ve bakım maliyeti ölçülmedi.",
]


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def n(v, d=0):
    return base.fnum(v, d)


def table(headers, rows, num_from=1):
    h = "".join(f"<th{' class=num' if i >= num_from else ''}>{esc(x)}</th>" for i, x in enumerate(headers))
    body = []
    for r in rows:
        tds = "".join(f"<td{' class=num' if i >= num_from else ''}>{c}</td>" for i, c in enumerate(r))
        body.append(f"<tr>{tds}</tr>")
    return f"<div class=tw><table><thead><tr>{h}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def findings(s, cats):
    g, sp = s["go"], s["spring"]
    out = []
    ratios = {p: g["phases"][p]["rps"] / sp["phases"][p]["rps"] for p in cats}
    hi = max(ratios, key=ratios.get)
    lo = min(ratios, key=ratios.get)
    out.append(f"<b>Throughput:</b> Go, {len(cats)} endpoint'in {sum(1 for r in ratios.values() if r > 1.1)} tanesinde Spring'den %10'dan fazla hızlı. "
               f"En büyük fark <b>{LABELS[hi]}</b> ({n(ratios[hi], 2)}x: {n(g['phases'][hi]['rps'])} vs {n(sp['phases'][hi]['rps'])} rps), "
               f"en küçük fark <b>{LABELS[lo]}</b> ({n(ratios[lo], 2)}x).")
    near = [LABELS[p] for p in cats if 0.9 <= ratios[p] <= 1.1]
    if near:
        out.append(f"<b>Eşit çıkanlar:</b> {', '.join(near)} - burada darboğaz uygulama değil {STORE_NAME}; iki dil de veri deposunu bekliyor.")
    avg = lambda st, m: sum(st["phases"][p][m] for p in cats) / len(cats)
    out.append(f"<b>Bellek:</b> yük altında ortalama Go <b>{n(avg(g, 'mem_avg_mib'))} MiB</b>, Spring Boot <b>{n(avg(sp, 'mem_avg_mib'))} MiB</b> "
               f"(~{n(avg(sp, 'mem_avg_mib') / avg(g, 'mem_avg_mib'), 0)}x). Boşta: {n(g['idle_mem_mib'])} MiB vs {n(sp['idle_mem_mib'])} MiB.")
    out.append(f"<b>Başlangıç:</b> Go {n(g['startup_s'], 1)} sn, Spring Boot {n(sp['startup_s'], 1)} sn "
               f"(konteyner başlat → /health 200). İlk istek: {n(g['first_request_ms'])} ms vs {n(sp['first_request_ms'])} ms.")
    light = [p for p in cats if p not in ("stats", "cpu", "fact", "report_all")]  # uzun süren işlerde p99/p50 anlamlı değil
    nl = max(len(light), 1)  # alt küme koşularında hafif endpoint olmayabilir
    tail_g = sum(g["phases"][p]["p99_ms"] / g["phases"][p]["p50_ms"] for p in light) / nl
    tail_s = sum(sp["phases"][p]["p99_ms"] / sp["phases"][p]["p50_ms"] for p in light) / nl
    out.append(f"<b>Gecikme kuyruğu:</b> p99/p50 oranı (DB'siz/çok ağır olmayan endpoint'lerde ortalama) Go'da ~{n(tail_g, 1)}x, "
               f"Spring'de ~{n(tail_s, 1)}x: Spring'in tipik gecikmesi düşük kalsa da en yavaş %1-5'lik dilim belirgin uzuyor.")
    out.append(f"<b>İmaj boyutu:</b> Go {n(g['image_mb'])} MB, Spring Boot {n(sp['image_mb'])} MB.")
    return out


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--fg:#1b1f24;--muted:#5d6670;--line:#e3e6ea;--go:#0a8fb3;--sp:#5a9e2f;--acc:#0b57d0}
@media (prefers-color-scheme:dark){:root{--bg:#14171a;--card:#1c2024;--fg:#e8eaed;--muted:#9aa3ad;--line:#2d3339;--go:#38b6d8;--sp:#86c85a;--acc:#8ab4f8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 -apple-system,"Segoe UI",Roboto,Arial,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:28px 16px 64px}
h1{font-size:1.9rem;line-height:1.25;margin:.2em 0 .1em}h2{font-size:1.3rem;margin:2.2em 0 .6em;padding-top:.4em;border-top:1px solid var(--line)}
h3{font-size:1.05rem;margin:1.6em 0 .4em}p{margin:.6em 0}.muted{color:var(--muted)}
.sub{color:var(--muted);margin:.2em 0 1.2em}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:18px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.card .k{color:var(--muted);font-size:.82rem}.card .v{font-size:1.5rem;font-weight:650;margin-top:2px}
.card .d{font-size:.85rem;color:var(--muted)}.go{color:var(--go)}.sp{color:var(--sp)}
ul.find{padding-left:1.2em}ul.find li{margin:.45em 0}
.tw{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:12px;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{padding:8px 12px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{background:color-mix(in srgb,var(--card) 92%,var(--fg));font-weight:600}tr:last-child td{border-bottom:0}.num{text-align:right;font-variant-numeric:tabular-nums}
.chart{background:#fff;border:1px solid var(--line);border-radius:12px;padding:6px;margin:12px 0;overflow-x:auto}.chart svg{max-width:100%;height:auto;display:block}
.note{background:color-mix(in srgb,var(--acc) 9%,var(--card));border:1px solid color-mix(in srgb,var(--acc) 30%,var(--line));border-radius:10px;padding:10px 14px;font-size:.92rem}
.warn{background:color-mix(in srgb,#e8a600 14%,var(--card));border-color:#e8a60066}
code,pre{font-family:Consolas,"Cascadia Mono",monospace;font-size:.88rem}pre{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;overflow-x:auto}
code{background:color-mix(in srgb,var(--card) 88%,var(--fg));padding:1px 5px;border-radius:5px}pre code{background:none;padding:0}
.sw{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:6px;vertical-align:baseline}
footer{margin-top:3em;color:var(--muted);font-size:.85rem}
"""


def tail_comment(tc):
    """CPU kotası ölçümünün özetini verilerden üretir (sabit sayı yazmaz)."""
    def pick(st, cpus):
        rows = [k for k in tc.get(st, []) if k.get("cpus") == cpus]
        return rows[0] if rows else None
    sp2, sp4, g2 = pick("spring", 2), pick("spring", 4), pick("go", 2)
    if not (sp2 and sp4 and g2 and sp2.get("throttled_pct") is not None and g2.get("throttled_pct") is not None):
        return "Ölçüm tablosu: konteyner CPU limiti arttıkça gecikme kuyruğunun ve kısıtlanmanın nasıl değiştiği."
    return (f"2 CPU limitinde Spring dönemlerin %{n(sp2['throttled_pct'], 0)}'inde, Go %{n(g2['throttled_pct'], 0)}'inde kısıtlanıyor. "
            f"Spring'in p95 gecikmesi 2 CPU'da {n(sp2['p95_ms'], 1)} ms, 4 CPU'da {n(sp4['p95_ms'], 1)} ms. "
            "Çok iş parçacıklı bir çalışma zamanı (JVM: Tomcat, GC, JIT) küçük bir kotada kısa süreli “patlama” yapıp CFS periyodunun geri kalanında "
            "bekletilebilir; bu bir <b>kaynak limiti etkileşimidir</b>, tek başına “JVM yavaştır” sonucu çıkarılamaz.")


def extras_html():
    """Ölçüm klasöründeki ek doğrulamaları (kuyruk, ısınma, indeks) ve varsa yöntem notlarını bölümlere çevirir."""
    res = OUT
    parts = []

    def load(name):
        p = res / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    tc = load("tail_check.json")
    if tc:
        rows = []
        for st in ("go", "spring"):
            for k in tc.get(st, []):
                rows.append([NAMES[st], f"{k['cpus']}", n(k["rps"]), n(k["p50_ms"], 1), n(k["p95_ms"], 1), n(k["p99_ms"], 1),
                             f"%{n(k['throttled_pct'], 1)}" if k.get("throttled_pct") is not None else "-", n(k["throttled_ms_per_s"])])
        parts.append("<h2>Spring'in gecikme kuyruğu neden uzun? (CPU kotası ölçümü)</h2>"
                     "<p>Aynı çalışan konteynerde <code>GET /items/{id}</code> yükü altında CPU limiti 2 → 4 → 2 yapıldı ve kernel'in cgroup "
                     "<code>cpu.stat</code> sayaçları okundu. “Kısıtlanan dönem”, 100 ms'lik CFS periyotlarının kaçında konteynerin kotayı aşıp "
                     "bekletildiğini gösterir.</p>" +
                     table(["Yığın", "CPU limiti", "rps", "p50 ms", "p95 ms", "p99 ms", "Kısıtlanan dönem", "Kısıtlama ms/sn"], rows) +
                     "<p class='muted'>" + tail_comment(tc) + "</p>")
    wc = load("warmup_check.json")
    if wc:
        rows = []
        for key, r in wc.items():
            st, w = key.split("-")
            rows.append([NAMES[st], f"{w} sn", n(r["health"][0]["rps"]), n(r["get"][0]["rps"]), n(r["health"][1]["rps"])])
        parts.append("<h2>Isınma süresi duyarlılığı</h2><p>Aynı konteyner, farklı ısınma süreleri. İlk ölçülen faz (health) JIT henüz bitmemişken "
                     "düşük çıkabilir.</p>" +
                     table(["Yığın", "Isınma", "health (ilk)", "get", "health (tekrar)"], rows) +
                     "<p class='muted'>İlk fazın (health) farklı ısınma sürelerindeki değeri: fark, JIT'in ısınma süresine duyarlılığını gösterir.</p>")
    ic = load("index_check.json")
    if ic:
        rows = []
        for ph in PHASES:
            if ph not in ic:
                continue
            r = ic[ph]
            used = ", ".join(f"{k} ({n(v)})" for k, v in r["index_scans"].items()) or "indeks kullanmaz"
            hot = f"%{n(100 * r['hot_updates'] / r['updates'])}" if r["updates"] else "-"
            rows.append([LABELS[ph], used, n(r["items_seq_scans"]), hot])
        parts.append("<h2>İndeks doğrulaması (pg_stat)</h2><p>Her endpoint 3 sn yüklenip PostgreSQL'in <code>pg_stat_user_indexes</code> ve "
                     "<code>pg_stat_user_tables</code> sayaçlarının farkı alındı.</p>" +
                     table(["Endpoint", "Kullanılan indeks (tarama sayısı)", "items seq scan", "HOT güncelleme"], rows, num_from=2) +
                     "<p class='muted'>Tablo taraması yapan endpoint'ler: " +
                     (", ".join(LABELS[p] for p in PHASES if p in ic and ic[p]["items_seq_scans"]) or "yok") +
                     ". HOT güncelleme, güncellemenin indeks bakımı gerektirmediği (hızlı) durumdur. Şemada yalnızca <code>items_pkey</code> ve "
                     "<code>lower(name)</code> indeksi tutulur; kullanılmayan her indeks yazmayı yavaşlatır.</p>")
    ab = load("index_ab.json")
    if ab:
        rows = []
        names = {"cover": "Kapsayan indeks (category) INCLUDE (price_cents, stock)", "plain_ff80": "Sade indeks + fillfactor=80"}
        for v, m in ab["mean"].items():
            rows.append([names.get(v, v), n(m["stats"]), n(m["update"]), n(m["order"]), f"%{n(m['hot_pct'])}"])
        parts.append("<h3>İndeks tasarımı A/B (Go, 2 tekrar, 64 eşzamanlı)</h3>" +
                     table(["Tasarım", "/stats rps", "PUT rps", "/orders rps", "HOT"], rows) +
                     "<p class='muted'>Kapsayan indeks tek sorguyu hızlandırdı (42 → ~20 ms) ama yük altında throughput kazandırmadı, güncellemeleri HOT "
                     "olmaktan çıkardı. Tekrarlar arası dalgalanma büyük; yön göstericidir.</p>")
    notes = OUT / "yontem_notlari.html"
    if notes.exists():
        parts.append(notes.read_text(encoding="utf-8"))
    return "".join(parts)


def comparison_html(s, base_s, base_meta, cur_meta):
    """Senaryo A -> B: aynı endpoint'in throughput değişimi."""
    cats = [p for p in PHASES if all(p in s[k]["phases"] and p in base_s.get(k, {}).get("phases", {}) for k in ("go", "spring"))]
    if not cats:
        return ""
    # /cpu veritabanı kullanmaz: A ile B arasında oranı 1'den farklıysa bu makine/oturum kaynaklı kaymadır (kontrol).
    ctrl = {}
    for k in ("go", "spring"):
        if "cpu" in cats:
            ctrl[k] = s[k]["phases"]["cpu"]["rps"] / base_s[k]["phases"]["cpu"]["rps"]
    rows = []
    for p in cats:
        row = [LABELS[p]]
        for k in ("go", "spring"):
            a, b = base_s[k]["phases"][p]["rps"], s[k]["phases"][p]["rps"]
            adj = f"{n((b / a) / ctrl[k], 2)}x" if k in ctrl else "-"
            row += [n(a), n(b), f"{n(b / a, 2)}x", adj]
        rows.append(row)
    t = table(["Endpoint", "Go A rps", "Go B rps", "Go B/A", "Go B/A (kontrole göre)",
               "Spring A rps", "Spring B rps", "Spring B/A", "Spring B/A (kontrole göre)"], rows)
    ctrl_note = ""
    if ctrl:
        ctrl_note = (f"<p class='note warn'><b>Kontrol ölçümü:</b> <code>/cpu</code> veritabanı kullanmaz, yine de A→B oranı Go'da "
                     f"<b>{n(ctrl['go'], 2)}x</b>, Spring'de <b>{n(ctrl['spring'], 2)}x</b> çıktı. Bu fark veritabanından değil, iki ölçüm oturumu arasındaki "
                     "makine durumundan (ısı, güç modu, arka plan yükü) gelir. Bu yüzden ham B/A oranları iyimserdir; "
                     "“kontrole göre” sütunları her oranı bu kayma kadar bölerek düzeltir (1,00x = veritabanı değişikliğinin etkisi yok).</p>")
    gap = []
    for p in cats:
        gap.append([LABELS[p], f"{n(base_s['go']['phases'][p]['rps'] / base_s['spring']['phases'][p]['rps'], 2)}x",
                    f"{n(s['go']['phases'][p]['rps'] / s['spring']['phases'][p]['rps'], 2)}x",
                    n(base_s['go']['phases'][p]['db_cpu_avg']), n(s['go']['phases'][p]['db_cpu_avg'])])
    t2 = table(["Endpoint", "Go/Spring (A)", "Go/Spring (B)", "DB CPU % (A, Go turu)", "DB CPU % (B, Go turu)"], gap)
    return (f"<p><b>A:</b> {esc(base_meta.get('db', ''))} <span class=muted>({esc(base_meta.get('note', ''))})</span><br>"
            f"<b>B:</b> {esc(cur_meta.get('db', ''))}</p>" + ctrl_note + t +
            "<h3>Go ile Spring arasındaki fark, veritabanı güçlenince nasıl değişti?</h3>" + t2 +
            "<p class='note'>B senaryosunda donanım (CPU/RAM), PostgreSQL ayarları ve indeks birlikte değişti; bu yüzden hangi değişikliğin ne kadar etkili "
            "olduğu ayrıştırılamaz. A yalnızca 1 turdur, B ortanca 3 turdur. Kapsayan indeks (category INCLUDE price_cents, stock) "
            "<code>/stats</code> sorgusunu hızlandırır, ancak <code>price_cents</code>/<code>stock</code> güncellemelerini HOT olmaktan çıkarıp "
            "yazma yollarına (<code>PUT /items/{id}</code>, <code>POST /orders</code>) ek indeks bakımı yükler.</p>")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "results"))
    ap.add_argument("--baseline", default="", help="önceki senaryo klasörü (summary.json içermeli)")
    args = ap.parse_args()
    global OUT
    base.configure(args.dir)
    OUT = base.OUT
    base.main()
    s = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    cur_meta = {}
    if (OUT / "scenario.json").exists():
        cur_meta = json.loads((OUT / "scenario.json").read_text(encoding="utf-8"))
    global STORE_NAME
    store = cur_meta.get("store", "postgres")
    STORE_NAME = {"postgres": "PostgreSQL", "valkey": "Valkey"}.get(store, store)
    comp_html = ""
    if args.baseline:
        bdir = Path(args.baseline).resolve()
        if (bdir / "summary.json").exists():
            base_meta = json.loads((bdir / "scenario.json").read_text(encoding="utf-8")) if (bdir / "scenario.json").exists() else {}
            comp_html = ("<h2>Veritabanını güçlendirmenin etkisi (A → B)</h2>" +
                         comparison_html(s, json.loads((bdir / "summary.json").read_text(encoding="utf-8")), base_meta, cur_meta))
    if "go" not in s or "spring" not in s:
        print("her iki yığının da en az 1 turu gerekli", file=sys.stderr)
        return 1
    vers = {}
    vf = base.RAW / "versions.json"
    if vf.exists():
        vers = json.loads(vf.read_text(encoding="utf-8"))
    g, sp = s["go"], s["spring"]
    cats = [p for p in PHASES if p in g["phases"] and p in sp["phases"]]
    rounds = min(g["rounds"], sp["rounds"])
    preliminary = rounds < 3 or len(cats) < 10
    today = datetime.date.today().isoformat()

    svg = {k: (base.CHARTS / f"{k}.svg").read_text(encoding="utf-8") for k in ("throughput", "latency_p99", "cpu", "memory")}

    # kartlar
    ratios = {p: g["phases"][p]["rps"] / sp["phases"][p]["rps"] for p in cats}
    avg = lambda st, m: sum(st["phases"][p][m] for p in cats) / len(cats)
    cards = [
        ("Throughput farkı (DB'siz /cpu)", f"{n(ratios.get('cpu', 0), 2)}x", "Go / Spring"),
        ("Throughput farkı (basit okuma /items/{id})", f"{n(ratios.get('get', 0), 2)}x", "Go / Spring"),
    ]
    for ph, lbl in (("cpu", "DB'siz /cpu"), ("get", "basit okuma /items/{id}")):
        ag, asp = g["phases"].get(ph, {}).get("avg_ms"), sp["phases"].get(ph, {}).get("avg_ms")
        if ag is not None and asp is not None:
            cards.append((f"Ortalama cevap süresi ({lbl})", f"<span class=go>{n(ag, 1)}</span> / <span class=sp>{n(asp, 1)}</span> ms", "Go / Spring"))
    cards += [
        ("Ortalama bellek (yük altında)", f"<span class=go>{n(avg(g, 'mem_avg_mib'))}</span> / <span class=sp>{n(avg(sp, 'mem_avg_mib'))}</span> MiB", "Go / Spring"),
        ("Soğuk başlangıç", f"<span class=go>{n(g['startup_s'], 1)}</span> / <span class=sp>{n(sp['startup_s'], 1)}</span> sn", "Go / Spring"),
        ("İmaj boyutu", f"<span class=go>{n(g['image_mb'])}</span> / <span class=sp>{n(sp['image_mb'])}</span> MB", "Go / Spring"),
    ]
    cards_html = "".join(f"<div class=card><div class=k>{esc(k)}</div><div class=v>{v}</div><div class=d>{esc(d)}</div></div>" for k, v, d in cards)

    # tablolar
    t_thr = table(["Endpoint", "Go rps", "Spring rps", "Go / Spring", "Go p50", "Spring p50", "Go p95", "Spring p95", "Go p99", "Spring p99"],
                  [[LABELS[p], n(g["phases"][p]["rps"]), n(sp["phases"][p]["rps"]), f"{n(ratios[p], 2)}x",
                    n(g["phases"][p]["p50_ms"], 1), n(sp["phases"][p]["p50_ms"], 1), n(g["phases"][p]["p95_ms"], 1),
                    n(sp["phases"][p]["p95_ms"], 1), n(g["phases"][p]["p99_ms"], 1), n(sp["phases"][p]["p99_ms"], 1)] for p in cats])
    t_res = table(["Endpoint", "Go CPU %", "Spring CPU %", "Go RAM MiB", "Spring RAM MiB", "Go RAM tepe", "Spring RAM tepe", "DB CPU % (Go)", "DB CPU % (Spring)"],
                  [[LABELS[p], n(g["phases"][p]["cpu_avg"]), n(sp["phases"][p]["cpu_avg"]), n(g["phases"][p]["mem_avg_mib"]),
                    n(sp["phases"][p]["mem_avg_mib"]), n(g["phases"][p]["mem_max_mib"]), n(sp["phases"][p]["mem_max_mib"]),
                    n(g["phases"][p]["db_cpu_avg"]), n(sp["phases"][p]["db_cpu_avg"])] for p in cats])
    t_eff = table(["Endpoint", "Go rps / %CPU", "Spring rps / %CPU", "Go avantajı"],
                  [[LABELS[p], n(g["phases"][p]["rps"] / g["phases"][p]["cpu_avg"], 1) if g["phases"][p]["cpu_avg"] else "-",
                    n(sp["phases"][p]["rps"] / sp["phases"][p]["cpu_avg"], 1) if sp["phases"][p]["cpu_avg"] else "-",
                    (n((g["phases"][p]["rps"] / g["phases"][p]["cpu_avg"]) / (sp["phases"][p]["rps"] / sp["phases"][p]["cpu_avg"]), 2) + "x")
                    if g["phases"][p]["cpu_avg"] and sp["phases"][p]["cpu_avg"] else "-"] for p in cats])
    cold_html = ""
    cold = s.get("cold")
    if cold and "go" in cold and "spring" in cold:
        cgo, csp = cold["go"], cold["spring"]
        crows = []
        for p in cats:
            if p in cgo["phases"] and p in csp["phases"]:
                x, y = cgo["phases"][p], csp["phases"][p]
                wg, ws = g["phases"][p]["rps"], sp["phases"][p]["rps"]
                crows.append([LABELS[p], n(x["rps"]), n(y["rps"]), f"{n(x['rps'] / y['rps'], 2)}x",
                              f"{n(x['rps'] / wg, 2)}x", f"{n(y['rps'] / ws, 2)}x", n(x["p99_ms"], 1), n(y["p99_ms"], 1)])
        cold_html = (f"<h2>Isınmasız tur ({cgo['phase_seconds']} sn faz)</h2>"
                     "<p>Normal turlardaki ısınma yükü (JIT ve bağlantı havuzu için) bu turda <b>yok</b>: konteyner taze başlar ve fazlar hemen ölçülür. "
                     "Her endpoint daha uzun (" + str(cgo['phase_seconds']) + " sn) ölçülür. Tek tur olduğundan sayılar ortanca değil tek ölçümdür.</p>" +
                     table(["Endpoint", "Go rps", "Spring rps", "Go / Spring", "Go ısınmasız / ısınmalı", "Spring ısınmasız / ısınmalı", "Go p99 ms", "Spring p99 ms"], crows) +
                     "<p class='muted'>“Isınmasız / ısınmalı” 1,00x'e yakınsa o endpoint ısınmadan etkilenmiyor demektir. "
                     "Fazlar sırayla koştuğundan JVM, önceki fazlarla zaten ısınır: ilk fazlar (health, list, get) en soğuk durumda ölçülür, sonrakiler daha ısınmış bir JVM'de. "
                     "Bu yüzden oranlar yukarıdan aşağı yükselebilir; ısınmanın etkisini en temiz ilk satırlar gösterir. Go için fark beklenmez (JIT yok).</p>")
    srv_html = ""
    if base.has_srv_time(s, ["go", "spring"], cats):
        def split(x):
            d, t = x["srv_data_ms"], x["srv_total_ms"]
            return d, (t - d) if (t is not None and d is not None) else None, (100 * d / t) if (t and d is not None) else None
        rows_srv = []
        for p in cats:
            gd, ga, gs = split(g["phases"][p])
            sd_, sa, ss = split(sp["phases"][p])
            rows_srv.append([LABELS[p], n(gd, 3), n(ga, 3), n(gs, 0), n(sd_, 3), n(sa, 3), n(ss, 0)])
        t_srv = table(["Endpoint", "Go veri ms", "Go uygulama ms", "Go veri %", "Spring veri ms", "Spring uygulama ms", "Spring veri %"], rows_srv)
        srv_svg = (base.CHARTS / "data_wait.svg").read_text(encoding="utf-8")
        srv_html = ("<h3>Veri bekleme süresi ve uygulama içi süre</h3>"
                    f"<div class='chart'>{srv_svg}</div>{t_srv}"
                    "<p class='muted'>Süreler uygulamanın <b>içinde</b> ölçülür ve yanıt başlığıyla (<code>Server-Timing</code>) iletilir; istek başına ortalama, ms. "
                    "<b>Veri</b>: veri deposuna sorgu/komut gönderilmesinden sonuçların uygulamaya okunup nesnelere çevrilmesine kadar geçen süre "
                    "(sürücü, ağ ve veri deposunda bekleme dahil; uygulamanın kendi mantığı dahil değil). "
                    "<b>Uygulama</b>: isteğin işleyiciye girişinden yanıtın yazılmaya başlamasına kadar geçen toplam süre eksi veri süresi "
                    "(ayrıştırma, toplama, rapor üretme; JSON gövdesinin yazılması ve HTTP çerçevesinin yanıt öncesi/sonrası işleri dahil değil). "
                    "<b>Veri %</b>: sunucu süresinin ne kadarının veriyi beklemekle geçtiği. "
                    "Yük altında (64 eşzamanlı istek) bu süreler boşta ölçüme göre uzun çıkar: veri deposundaki ya da bağlantı havuzundaki kuyruk da beklemeye dahildir. "
                    "Her iki dilin işleyicilerine aynı yerlerden ölçüm konmuştur. <code>POST /orders</code>'ta Spring tarafında transaction elle yönetilir "
                    "(başlatma, iki sorgu ve commit tek veri bloğu); Go'da da aynı kapsamdadır.</p>")
    cpu_time_html = ""
    if base.has_cpu_time(s, ["go", "spring"], cats):
        rr = lambda p: (sp["phases"][p]["app_cpu_ms_per_req"] / g["phases"][p]["app_cpu_ms_per_req"]) if g["phases"][p]["app_cpu_ms_per_req"] else None
        t_cput = table(["Endpoint", "Go CPU sn", "Spring CPU sn", "Go ms/istek", "Spring ms/istek", "Spring / Go",
                        "Veri deposu CPU sn (Go)", "Veri deposu CPU sn (Spring)"],
                       [[LABELS[p], n(g["phases"][p]["app_cpu_s"], 1), n(sp["phases"][p]["app_cpu_s"], 1),
                         n(g["phases"][p]["app_cpu_ms_per_req"], 3), n(sp["phases"][p]["app_cpu_ms_per_req"], 3),
                         (n(rr(p), 2) + "x") if rr(p) else "-",
                         n(g["phases"][p]["db_cpu_s"], 1), n(sp["phases"][p]["db_cpu_s"], 1)] for p in cats])
        cpu_svg = (base.CHARTS / "cpu_per_req.svg").read_text(encoding="utf-8")
        cpu_time_html = (f"<h3>CPU çalışma süresi</h3><div class='chart'>{cpu_svg}</div>{t_cput}"
                         "<p class='muted'>CPU süresi, konteynerin cgroup sayacından (<code>cpu.stat</code> &gt; <code>usage_usec</code>) okunur: "
                         "yük süresince çekirdeklerde harcanan toplam kullanıcı + çekirdek süresi (saniye). "
                         "“ms/istek” bu süreyi tamamlanan istek sayısına böler: aynı işi yapmak için ne kadar CPU harcandığını, "
                         "kotaya ve throughput'a bağlı olmadan gösterir. Süre, fazın başında ve sonunda iki okumanın farkıdır; "
                         "arada birkaç saniyelik boşta kalma payı vardır (ihmal edilebilir).</p>")
    t_gen = table(["Metrik", "Go", "Spring Boot"], [
        ["Soğuk başlangıç (konteyner → /health 200; /health veri deposuna dokunmaz), sn", n(g["startup_s"], 2), n(sp["startup_s"], 2)],
        ["Spring'in kendi bildirdiği açılış süresi, sn", "-", n(sp["jvm_started_s"], 2) if sp.get("jvm_started_s") else "-"],
        ["İlk istek gecikmesi, ms", n(g["first_request_ms"]), n(sp["first_request_ms"])],
        ["İkinci istek gecikmesi, ms", n(g["second_request_ms"], 1), n(sp["second_request_ms"], 1)],
        ["Boşta bellek, MiB", n(g["idle_mem_mib"]), n(sp["idle_mem_mib"])],
        ["Isınma sonrası bellek, MiB", n(g["after_warmup_mem_mib"]), n(sp["after_warmup_mem_mib"])],
        ["Test boyunca en yüksek bellek, MiB", n(g["peak_mem_mib"]), n(sp["peak_mem_mib"])],
        ["İmaj boyutu, MB", n(g["image_mb"]), n(sp["image_mb"])],
    ])
    t_err = table(["Endpoint", "Go hata %", "Spring hata %", "Go rps (min–maks tur)", "Spring rps (min–maks tur)"],
                  [[LABELS[p], n(g["phases"][p]["error_rate"] * 100, 2), n(sp["phases"][p]["error_rate"] * 100, 2),
                    f"{n(g['phases'][p]['rps_min'])}–{n(g['phases'][p]['rps_max'])}",
                    f"{n(sp['phases'][p]['rps_min'])}–{n(sp['phases'][p]['rps_max'])}"] for p in cats])

    # build süresi (scripts/build_time.py çalıştırıldıysa)
    build_html = ""
    bf = base.RAW / "build_times.json"
    if bf.exists():
        b = json.loads(bf.read_text(encoding="utf-8"))
        if "go" in b and "spring" in b:
            def span(x):
                return f"{n(min(x), 1)}–{n(max(x), 1)}"
            t_b = table(["Build", "Go", "Spring Boot", "Spring / Go"], [
                ["Temiz build (önbelleksiz, bağımlılık indirme dahil), sn ortanca", n(b["go"]["clean_median_s"], 1),
                 n(b["spring"]["clean_median_s"], 1), f"{n(b['spring']['clean_median_s'] / b['go']['clean_median_s'], 1)}x"],
                ["   en düşük–en yüksek, sn", span(b["go"]["clean_s"]), span(b["spring"]["clean_s"]), ""],
                ["Artımlı build (yalnızca kod değişti), sn ortanca", n(b["go"]["incremental_median_s"], 1),
                 n(b["spring"]["incremental_median_s"], 1), f"{n(b['spring']['incremental_median_s'] / b['go']['incremental_median_s'], 1)}x"],
                ["   en düşük–en yüksek, sn", span(b["go"]["incremental_s"]), span(b["spring"]["incremental_s"]), ""],
            ])
            build_html = ("<h3>Build süresi</h3>" + t_b +
                          "<p class='muted'>Docker çok aşamalı build (derleme + çalışma imajı), "
                          f"{len(b['go']['clean_s'])} tekrar. Taban imajların indirilmesi dahil değil; temiz buildde Go modülleri ve Maven bağımlılıkları "
                          "yeniden indirilir, bu yüzden ağ hızından etkilenir. Artımlı build, bağımlılık katmanları önbellekteyken yalnızca kodun değiştiği günlük geliştirme durumudur. "
                          f"Go'nun artımlı build'i ~{n(b['go']['incremental_median_s'], 0)} sn'de kalır: Docker, Go derleme önbelleğini katmanlar arasında taşımadığı için pgx her seferinde yeniden derlenir "
                          "(BuildKit cache mount ile çok düşmesi beklenir, ölçülmedi). Spring'de bağımlılık jar'ları katmanda hazır olduğundan yalnızca kendi kodu derlenir. "
                          "Burada yalnızca Docker build'i ölçüldü; Docker dışı yerel derleme süresi ölçülmedi.</p>")
            cards.append(("Temiz build süresi", f"<span class=go>{n(b['go']['clean_median_s'], 0)}</span> / <span class=sp>{n(b['spring']['clean_median_s'], 0)}</span> sn", "Go / Spring"))
            cards.append(("Artımlı build süresi", f"<span class=go>{n(b['go']['incremental_median_s'], 0)}</span> / <span class=sp>{n(b['spring']['incremental_median_s'], 0)}</span> sn", "Go / Spring"))
            cards_html = "".join(f"<div class=card><div class=k>{esc(k)}</div><div class=v>{v}</div><div class=d>{esc(d)}</div></div>" for k, v, d in cards)

    endpoints = table(["#", "Endpoint", "Ne yapar", "İş yükü"], [
        ["1", "GET /health", "Canlılık (yalnızca uygulama, veri deposu yok)", "Sabit yanıt: HTTP çerçevesinin ham maliyeti"],
        ["2", "GET /items?after=&limit=", "Sayfalı liste (50 kayıt)", "Keyset sayfalama, indeksli"],
        ["3", "GET /items/{id}", "Tek kayıt okuma", "Birincil anahtar araması"],
        ["4", "POST /items", "Kayıt ekleme", "INSERT ... RETURNING"],
        ["5", "PUT /items/{id}", "Kayıt güncelleme", "UPDATE ... RETURNING"],
        ["6", "DELETE /items/{id}", "Kayıt silme", "DELETE (ayrılmış 800.000 satırlık aralıkta)"],
        ["7", "GET /items/search?q=", "Önek araması", "lower(name) LIKE 'xxxx%', text_pattern_ops indeksi"],
        ["8", "GET /stats", "Kategori istatistikleri", "100.000 satırda GROUP BY, ağır toplama"],
        ["9", "POST /orders", "Sipariş oluşturma", "Tek transaction: stok düş + sipariş ekle"],
        ["10", "GET /cpu?n=50000", "Saf CPU işi (DB yok)", "50.000'e kadar asal sayı sayma (deneme bölmesi)"],
        ["11", "GET /stores/{id}/sales-report", "Tek mağazanın günlük + aylık satış raporu",
         "Mağazanın ~2.000 satış satırı çekilir; günlük/aylık toplamlar, en iyi gün, aylık büyüme <b>uygulama kodunda</b> hesaplanır"],
        ["12", "GET /reports/sales", "Tüm mağazalar, mağaza mağaza rapor (hesap veritabanında)",
         "Günlük ve aylık toplamlar <b>veritabanında</b> (SQL <code>GROUP BY</code>) hesaplanır; uygulama yalnızca hazır toplamları rapora dizer (en iyi gün, büyüme %)"],
        ["13", "POST /base64", "İsteğin gövdesini Base64'e çevirir (DB yok)",
         "~2 KB'lık gövde okunur, standart Base64'e kodlanır ve JSON olarak döner"],
        ["14", "GET /factorial?n=1000", "1000! hesaplar (DB yok)",
         "Büyük tamsayıyla (big.Int / BigInteger) <b>sıralı çarpma</b>, ardından ondalık metne çevirme; basamak sayısı, ilk 16 basamak ve sondaki sıfır sayısı döner"],
    ], num_from=99)

    if store == "valkey":
        endpoints = table(["#", "Endpoint", "Ne yapar", "İş yükü (Valkey)"], [
            ["1", "GET /health", "Canlılık (yalnızca uygulama, veri deposu yok)", "Sabit yanıt: HTTP çerçevesinin ham maliyeti"],
            ["2", "GET /items?after=&limit=", "Sayfalı liste (50 kayıt)", "ZRANGEBYSCORE (sorted set, skor = id) + 50 HMGET (tek pipeline)"],
            ["3", "GET /items/{id}", "Tek kayıt okuma", "HMGET (hash)"],
            ["4", "POST /items", "Kayıt ekleme", "Lua: INCR + HSET + 2 × ZADD (tek tur)"],
            ["5", "PUT /items/{id}", "Kayıt güncelleme", "Lua: HSET + HMGET"],
            ["6", "DELETE /items/{id}", "Kayıt silme", "Lua: HGET + DEL + 2 × ZREM (ayrılmış 2.000.000 kayıtlık aralıkta)"],
            ["7", "GET /items/search?q=", "Önek araması", "ZRANGEBYLEX (üye: küçük harfli ad + kimlik) + HMGET pipeline"],
            ["8", "POST /orders", "Sipariş oluşturma", "Lua: stok kontrolü + düşme + sipariş kaydı (atomik, tek tur)"],
            ["9", "GET /cpu?n=50000", "Saf CPU işi (veri deposu yok)", "50.000'e kadar asal sayı sayma (deneme bölmesi)"],
            ["10", "GET /stores/{id}/sales-report", "Tek mağazanın günlük + aylık satış raporu",
             "LRANGE ile mağazanın ~2.000 satış kaydı çekilir; günlük/aylık toplamlar, en iyi gün, aylık büyüme <b>uygulama kodunda</b> hesaplanır"],
            ["11", "GET /reports/sales", "Tüm mağazalar, mağaza mağaza rapor (hesap Valkey içinde)",
             "Lua betiği 20 mağazanın 40.000 kaydını sunucuda gün/ay toplamlarına çevirir (SQL <code>GROUP BY</code>'ın karşılığı); uygulama hazır toplamları rapora dizer"],
            ["12", "POST /base64", "İsteğin gövdesini Base64'e çevirir (veri deposu yok)",
             "~2 KB'lık gövde okunur, standart Base64'e kodlanır ve JSON olarak döner"],
            ["13", "GET /factorial?n=1000", "1000! hesaplar (veri deposu yok)",
             "Büyük tamsayıyla <b>sıralı çarpma</b>, ardından ondalık metne çevirme"],
        ], num_from=99)
        endpoints += (
            "<h3>Bu senaryonun PostgreSQL senaryosundan farkları</h3><ul class='find'>"
            "<li><b><code>/stats</code> yok:</b> SQL <code>GROUP BY</code>'ın bellek içi depoda doğal bir karşılığı yok; yapay bir karşılık yazılmadı.</li>"
            "<li><b>Yazmalar Lua betiğiyle tek turda:</b> ekleme, güncelleme, silme ve sipariş tek atomik komuttur (PostgreSQL'deki transaction'ın karşılığı). "
            "Valkey komutları tek iş parçacığında yürüttüğü için ağır betikler diğer isteklerin önüne geçer.</li>"
            "<li><b>İstemciler:</b> Go: go-redis (havuz 20, pipeline). Spring: Jedis (bloklayan istemci, havuz 20, pipeline). "
            "Her dilin yaygın istemcisi seçildi; başka istemci (ör. Lettuce) sonucu değiştirebilir.</li>"
            "<li><b>Satış raporları:</b> ham satırlar liste olarak saklanır (<code>epoch|adet|tutar</code>). Tek mağaza raporunda toplamlar <b>uygulama kodunda</b> hesaplanır; "
            "<code>/reports/sales</code>'te ise <b>Valkey içinde</b> bir Lua betiğiyle. Valkey komutları tek iş parçacığında yürüttüğünden bu betik çalışırken sunucu başka isteğe bakmaz: "
            "bu endpoint'te veri deposu darboğaza dönüşebilir (PostgreSQL'deki <code>/stats</code> gibi).</li>"
            "<li><b>Arama:</b> <code>ZRANGEBYLEX</code> ile önek araması, en fazla 20 sonuç, kimliğe göre sıralı. 4 karakterlik önekte PostgreSQL ile aynı sonucu verir (doğrulandı).</li>"
            "<li><b>Aynı çıktı:</b> iki uygulamanın iki veri deposundaki JSON çıktıları 19 örnek istekte birebir aynıdır (tek kayıt, liste, arama, 404/409, ekleme, güncelleme, silme, sipariş, satış raporları).</li>"
            "<li><b>Kalıcılık kapalı</b> (<code>save \"\"</code>, <code>appendonly no</code>): yalnızca benchmark içindir; üretimde veri kaybı riski taşır.</li>"
            "</ul>")


    pr = {}
    for f in sorted(base.RAW.glob("run-r*-*.json")):
        pr = json.loads(f.read_text(encoding="utf-8"))
        break
    warm_s, phase_s, vus = pr.get("warmup_seconds", 180), pr.get("phase_seconds", 20), pr.get("vus", 64)

    lim_cpu = n(base.LIMITS["cpus"], 1 if base.LIMITS["cpus"] % 1 else 0)
    lim_mem = esc(base.LIMITS["mem"])
    env_rows = [
        ["Donanım", esc(cur_meta.get("hardware") or "kaydedilmedi")],
        ["Docker", esc(vers.get("docker", "")) + ("; " + esc(vers["host"]) if vers.get("host") else "")],
        ["Güç durumu (test başında)", esc(vers.get("power", "kaydedilmedi"))],
        ["Uygulama limitleri", f"Her API konteyneri: <b>{lim_cpu} CPU, {lim_mem} RAM</b> (aynı anda yalnızca biri çalışır)"],
        (["Veri deposu", f"{esc(vers.get('valkey', 'Valkey 8'))}; {esc(cur_meta.get('db', '-'))}; 100.000 ürün + 20 mağaza + 40.000 satış kaydı "
                         "(PostgreSQL senaryosuyla birebir aynı deterministik veri)"]
         if store == "valkey" else
         ["Veritabanı", f"{esc(vers.get('postgres', 'PostgreSQL 18'))}; {esc(cur_meta.get('db', '-'))}; 100.000 ürün"]),
        ["Senaryo", esc(cur_meta.get("name", "-"))],
        ["Go", f"{esc(vers.get('go', 'Go 1.27'))}; net/http (standart) + " +
               ("go-redis v9 (havuz 20)" if store == "valkey" else "pgx v5 (havuz 20)") + "; scratch imajı"],
        ["Java / Spring Boot", f"{esc(vers.get('java', 'Java 25'))}; Spring Boot 4.2.0, Spring MVC (Tomcat) + " +
                               ("Jedis (bloklayan istemci, havuz 20)" if store == "valkey" else "JdbcClient + Hikari (havuz 20)") +
                               "; -XX:MaxRAMPercentage=50"],
        ["Yük aracı", f"{esc(vers.get('k6', 'k6'))}; {vus} eşzamanlı sanal kullanıcı, bekleme yok"],
    ]
    t_env = table(["Bileşen", "Ayrıntı"], env_rows, num_from=99)

    yp = OUT / "yorum.html"
    yorum_html = f"<h2>Yorum</h2>{yp.read_text(encoding='utf-8')}" if yp.exists() else ""
    prelim = ("<div class='note warn'><b>Ön sonuç.</b> Bu rapor şu ana kadar tamamlanan ölçümlerle üretildi "
              f"({rounds} tam tur, {len(cats)} endpoint). Test bitince aynı komutla yenilenir.</div>") if preliminary else ""

    html = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Go vs Spring Boot Performans Karşılaştırması ({STORE_NAME})</title><style>{CSS}</style></head><body><div class="wrap">
<h1>Go vs Spring Boot: Performans Karşılaştırması{' (Valkey)' if store == 'valkey' else ''}</h1>
<p class="sub">Aynı {len(cats)} endpoint, aynı {STORE_NAME}, aynı Docker kaynak limitleri ({lim_cpu} CPU / {lim_mem}). Rapor tarihi: {today}. {rounds} tur ortancası.</p>
{prelim}
<div class="cards">{cards_html}</div>

<h2>Özet</h2>
<ul class="find">{''.join(f'<li>{f}</li>' for f in findings(s, cats))}</ul>

<h2>Test ortamı</h2>{t_env}

<h2>Metodoloji</h2>
<ul class="find">
{('<li><b>Her tur taze başlar:</b> Valkey <code>FLUSHALL</code> ile boşaltılıp aynı tohum veri yeniden yüklenir, API konteyneri sıfırdan (soğuk) başlatılır.</li>' if store == 'valkey' else '<li><b>Her tur taze başlar:</b> <code>bench</code> veritabanı şablondan yeniden oluşturulur, API konteyneri sıfırdan (soğuk) başlatılır.</li>')}
{(f'<li><b>Isınma:</b> {warm_s} sn karışık yük (JIT ve bağlantı havuzu ısınsın); ölçüme dahil değil. Isınmanın eklediği ya da değiştirdiği her şey silinir, depo her iki yığın için de aynı tohum veriyle yeniden yüklenir.</li>' if store == 'valkey' else f'<li><b>Isınma:</b> {warm_s} sn karışık yük (JIT ve bağlantı havuzu ısınsın); ölçüme dahil değil. Isınmanın eklediği satırlar silinip tablo her iki yığın için de aynı 100.000 satıra döndürülür (<code>VACUUM FULL</code>), böylece <code>/stats</code> aynı veri boyutunda ölçülür.</li>')}
<li><b>Ölçüm:</b> her endpoint {phase_s} sn, {vus} eşzamanlı sanal kullanıcı, kapalı döngü (istek biter bitmez yenisi). Sırayla {len(cats)} endpoint.</li>
<li><b>Adillik:</b> {'aynı Lua betikleri ve komutlar' if store == 'valkey' else 'aynı SQL'}, aynı bağlantı havuzu boyutu (20), aynı kaynak limiti, aynı veri; yığınlar aynı anda değil sırayla koşar, tur sırası dönüşümlü (Go→Spring, Spring→Go, Go→Spring).</li>
<li><b>Ölçülenler:</b> throughput (rps), gecikme (p50/p95/p99), uygulama ve veritabanı CPU'su, uygulama belleği (docker stats, ~1 Hz), hata oranı (2xx dışı), başlangıç süresi, ilk istek gecikmesi, imaj boyutu.</li>
<li><b>Tur sonucu:</b> {rounds} turun ortancası; en düşük–en yüksek aralık "Hata oranı ve tur farkı" tablosunda.</li>
</ul>

<h2>Endpoint'ler</h2>{endpoints}

<h2>Throughput</h2>
<div class="chart">{svg['throughput']}</div>
<h2>Gecikme</h2>
<div class="chart">{svg['latency_p99']}</div>
<h3>Throughput ve gecikme tablosu (ms)</h3>{t_thr}
{cold_html}

<h2>Kaynak kullanımı</h2>
<div class="chart">{svg['cpu']}</div>
<div class="chart">{svg['memory']}</div>
<h3>CPU ve RAM (yük altında)</h3>{t_res}
{cpu_time_html}
{srv_html}
<h3>CPU başına throughput</h3>{t_eff}
<p class="muted">CPU değeri docker stats'tan gelir: %100 = bir çekirdek, bu testte üst sınır %{n(base.LIMITS["cpus"] * 100)}.</p>

<h2>Başlangıç, imaj ve build süresi</h2>{t_gen}{build_html}

{comp_html}

{yorum_html}

{extras_html()}

<h2>Sınırlılıklar</h2>
<ul class="find">{''.join(f'<li>{esc(x)}</li>' for x in SINIRLILIK)}</ul>

<h2>Hata oranı ve tur farkı</h2>{t_err}

<h2>Yeniden üretme</h2>
<pre><code>git clone &lt;repo&gt; &amp;&amp; cd go-vs-spring-bench
docker compose run --rm runner            # tam koşu (build + ölçüm + rapor) -> results/report.html
docker compose run --rm runner --quick    # kısa deneme koşusu</code></pre>
<footer>Ham ölçümler: raw/ · Özet: summary.json · Kaynak kod: bu depo</footer>
</div></body></html>"""
    (OUT / "report.html").write_text(html, encoding="utf-8")
    print("yazildi:", OUT / "report.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
