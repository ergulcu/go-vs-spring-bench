#!/usr/bin/env python3
"""results/raw/run-*.json dosyalarından özet (summary.json), Markdown tabloları (tables.md) ve SVG grafikler üretir."""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "results" / "raw"
OUT = ROOT / "results"
CHARTS = OUT / "charts"
PHASES = ["health", "list", "get", "search", "stats", "cpu", "order", "create", "update", "delete", "report_store", "report_all", "b64", "fact"]
LABELS = {
    "health": "GET /health", "list": "GET /items", "get": "GET /items/{id}", "search": "GET /items/search",
    "stats": "GET /stats", "cpu": "GET /cpu", "order": "POST /orders", "create": "POST /items",
    "update": "PUT /items/{id}", "delete": "DELETE /items/{id}",
    "report_store": "GET /stores/{id}/sales-report", "report_all": "GET /reports/sales",
    "b64": "POST /base64", "fact": "GET /factorial?n=1000",
}
COLORS = {"go": "#0a8fb3", "spring": "#5a9e2f"}
NAMES = {"go": "Go", "spring": "Spring Boot"}


LIMITS = {"cpus": 2, "mem": "2 GiB", "mem_mib": 2048}


def configure(directory):
    """Başka bir senaryo klasörünü (içinde raw/ olan) hedef al: results/scenario-a gibi."""
    global RAW, OUT, CHARTS
    OUT = Path(directory).resolve()
    RAW = OUT / "raw"
    CHARTS = OUT / "charts"
    meta = {}
    if (OUT / "scenario.json").exists():
        meta = json.loads((OUT / "scenario.json").read_text(encoding="utf-8"))
    LIMITS["cpus"] = meta.get("app_cpus", 2)
    LIMITS["mem"] = meta.get("app_mem", "2 GiB")
    LIMITS["mem_mib"] = meta.get("app_mem_mib", 2048)


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def load():
    runs = {"go": [], "spring": []}
    for f in sorted(RAW.glob("run-r*-*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        runs[d["stack"]].append(d)
    return runs


def load_cold():
    """Isınmasız tur sonuçları (run-c*-*.json); yığın başına tek tur."""
    out = {}
    for f in sorted(RAW.glob("run-c*-*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out[d["stack"]] = d
    return out


def summarize_cold(cold_runs):
    if "go" not in cold_runs or "spring" not in cold_runs:
        return None
    res = {}
    for stack, d in cold_runs.items():
        res[stack] = {"phase_seconds": d.get("phase_seconds"), "startup_s": d.get("startup_s"),
                      "phases": {ph: {"rps": p["rps"], "p50_ms": p["p50_ms"], "p95_ms": p["p95_ms"], "p99_ms": p["p99_ms"],
                                      "error_rate": p["error_rate"], "srv_data_ms": p.get("srv_data_avg_ms"),
                                      "srv_total_ms": p.get("srv_total_avg_ms")}
                                 for ph, p in d["phases"].items()}}
    return res


def summarize(runs):
    s = {}
    for stack, rs in runs.items():
        if not rs:
            continue
        g = {"rounds": len(rs),
             "startup_s": med([r["startup_s"] for r in rs]),
             "jvm_started_s": med([r.get("jvm_started_s") for r in rs]),
             "first_request_ms": med([r["first_request_ms"] for r in rs]),
             "second_request_ms": med([r["second_request_ms"] for r in rs]),
             "idle_mem_mib": med([r["idle"]["mem_mib"] for r in rs]),
             "after_warmup_mem_mib": med([r["after_warmup"]["mem_mib"] for r in rs]),
             "image_mb": med([r["image_bytes"] for r in rs]) / 1e6,
             "phases": {}}
        for ph in PHASES:
            ps = [r["phases"][ph] for r in rs if ph in r["phases"]]
            if not ps:
                continue
            g["phases"][ph] = {
                "rps": med([p["rps"] for p in ps]),
                "rps_min": min(p["rps"] for p in ps), "rps_max": max(p["rps"] for p in ps),
                "avg_ms": med([p.get("avg_ms") for p in ps]),
                "p50_ms": med([p["p50_ms"] for p in ps]), "p95_ms": med([p["p95_ms"] for p in ps]),
                "p99_ms": med([p["p99_ms"] for p in ps]),
                "error_rate": med([p["error_rate"] for p in ps]),
                "cpu_avg": med([p["app"]["cpu_avg"] for p in ps if p.get("app")]),
                "mem_avg_mib": med([p["app"]["mem_avg_mib"] for p in ps if p.get("app")]),
                "mem_max_mib": med([p["app"]["mem_max_mib"] for p in ps if p.get("app")]),
                "db_cpu_avg": med([p["db"]["cpu_avg"] for p in ps if p.get("db")]),
                # cgroup sayacından: harcanan toplam CPU süresi (sn) ve istek başına CPU süresi (ms). Eski verilerde yoktur (None).
                # sunucu tarafı süre ölçümü (Server-Timing): veri deposunu beklerken geçen süre ve toplam sunucu süresi, ms. Eski verilerde yoktur (None).
                "srv_data_ms": med([p.get("srv_data_avg_ms") for p in ps]),
                "srv_total_ms": med([p.get("srv_total_avg_ms") for p in ps]),
                "srv_data_p95_ms": med([p.get("srv_data_p95_ms") for p in ps]),
                "app_cpu_s": med([p["cpu_time"].get("app_s") for p in ps if p.get("cpu_time")]),
                "app_cpu_ms_per_req": med([p["cpu_time"].get("app_ms_per_req") for p in ps if p.get("cpu_time")]),
                "db_cpu_s": med([p["cpu_time"].get("db_s") for p in ps if p.get("cpu_time")]),
                "db_cpu_ms_per_req": med([p["cpu_time"].get("db_ms_per_req") for p in ps if p.get("cpu_time")]),
            }
        g["peak_mem_mib"] = max((p["mem_max_mib"] for p in g["phases"].values()), default=None)
        s[stack] = g
    return s


# ------------------------------------------------------------------ SVG
def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def grouped_hbars(path, title, subtitle, cats, series, values, fmt, per_row=True, extra=None):
    """values[stack][cat] -> sayı. per_row=True: her satırın en uzun çubuğu tam genişlik.
    extra[stack][cat] -> çubuğun ucundaki etikete eklenen ikinci değer (metin), yoksa yok."""
    W, left, barmax, row_h, top = 960, 150, 560, 48, 78
    H = top + row_h * len(cats) + 56
    gmax = max((v for s in series for v in values[s].values() if v), default=1)
    o = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {W} {H}' width='{W}' height='{H}' font-family='Segoe UI, Arial, sans-serif'>",
         f"<rect width='{W}' height='{H}' fill='#ffffff'/>",
         f"<text x='20' y='30' font-size='17' font-weight='600' fill='#1a1a1a'>{esc(title)}</text>",
         f"<text x='20' y='50' font-size='12' fill='#666666'>{esc(subtitle)}</text>"]
    for i, c in enumerate(cats):
        y = top + i * row_h
        row_max = max((values[s].get(c) or 0 for s in series), default=1) or 1
        scale_max = row_max if per_row else gmax
        o.append(f"<text x='{left - 10}' y='{y + 22}' font-size='12' text-anchor='end' fill='#333333'>{esc(LABELS.get(c, c))}</text>")
        for j, s in enumerate(series):
            v = values[s].get(c)
            if v is None:
                continue
            w = max(1.5, v / scale_max * barmax)
            by = y + j * 19 + 4
            o.append(f"<rect x='{left}' y='{by}' width='{w:.1f}' height='15' rx='2' fill='{COLORS[s]}'/>")
            label = fmt(v)
            if extra and extra.get(s, {}).get(c) is not None:
                label += f" · {extra[s][c]}"
            o.append(f"<text x='{left + w + 6:.1f}' y='{by + 12}' font-size='11' fill='#333333'>{esc(label)}</text>")
    ly = H - 24
    lx = left
    for s in series:
        o.append(f"<rect x='{lx}' y='{ly - 10}' width='12' height='12' rx='2' fill='{COLORS[s]}'/>")
        o.append(f"<text x='{lx + 18}' y='{ly}' font-size='12' fill='#333333'>{esc(NAMES[s])}</text>")
        lx += 130
    note = "Her satırda en uzun çubuk %100 genişliktir; gerçek değer çubuğun yanında." if per_row else "Tüm satırlar aynı ölçekte."
    o.append(f"<text x='{W - 20}' y='{ly}' font-size='11' text-anchor='end' fill='#777777'>{note}</text>")
    o.append("</svg>")
    path.write_text("\n".join(o), encoding="utf-8")


def has_srv_time(s, stacks, cats):
    """Her yığın ve her endpoint için sunucu tarafı süre ölçümü (Server-Timing) var mı?"""
    return bool(cats) and all(s[k]["phases"][p].get("srv_data_ms") is not None for k in stacks for p in cats)


def has_cpu_time(s, stacks, cats):
    """Her yığın ve her endpoint için CPU süresi ölçülmüş mü? (Eski sonuç dosyalarında yok.)"""
    return bool(cats) and all(s[k]["phases"][p].get("app_cpu_ms_per_req") is not None for k in stacks for p in cats)


def fnum(v, d=0):
    """Türkçe sayı biçimi: binlik ayracı nokta, ondalık ayracı virgül (1.234,5)."""
    if v is None:
        return "-"
    return f"{v:,.{d}f}".replace(",", "\0").replace(".", ",").replace("\0", ".")


def main():
    runs = load()
    s = summarize(runs)
    if not s:
        print("sonuc yok", file=sys.stderr)
        return 1
    cold = summarize_cold(load_cold())
    if cold:
        s["cold"] = cold
    OUT.mkdir(exist_ok=True)
    CHARTS.mkdir(exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    stacks = [k for k in ("go", "spring") if k in s]
    cats = [p for p in PHASES if all(p in s[k]["phases"] for k in stacks)]

    def val(metric):
        return {k: {p: s[k]["phases"][p][metric] for p in cats} for k in stacks}

    # çubuk ucundaki etikete eklenen ortalama cevap süresi (eski verilerde yoksa eklenmez)
    avg_labels = {k: {p: (f"ort. {fnum(s[k]['phases'][p]['avg_ms'], 1)} ms" if s[k]["phases"][p].get("avg_ms") is not None else None)
                      for p in cats} for k in stacks}
    grouped_hbars(CHARTS / "throughput.svg", "Throughput (istek/sn, yüksek iyi)",
                  f"64 eşzamanlı kullanıcı, {fnum(LIMITS['cpus'], 1 if LIMITS['cpus'] % 1 else 0)} CPU / {LIMITS['mem']} limitli uygulama, tur ortancası", cats, stacks, val("rps"),
                  lambda v: f"{fnum(v)} rps", extra=avg_labels)
    grouped_hbars(CHARTS / "latency_p99.svg", "p99 gecikme (ms, düşük iyi)",
                  "Aynı yük altında istek gecikmesinin 99. yüzdeliği", cats, stacks, val("p99_ms"), lambda v: f"{fnum(v, 1)} ms", extra=avg_labels)
    grouped_hbars(CHARTS / "cpu.svg", f"Uygulama CPU kullanımı (% - {fnum(LIMITS['cpus'] * 100)} = limit dolu)",
                  "Yük süresince docker stats ortalaması", cats, stacks, val("cpu_avg"), lambda v: f"%{fnum(v)}", per_row=False)
    grouped_hbars(CHARTS / "memory.svg", "Uygulama bellek kullanımı (MiB, yük altında ortalama)",
                  f"Docker konteyner belleği (RSS + önbellek), limit {LIMITS['mem_mib']} MiB", cats, stacks, val("mem_avg_mib"),
                  lambda v: f"{fnum(v)} MiB", per_row=False)

    if has_cpu_time(s, stacks, cats):
        grouped_hbars(CHARTS / "cpu_per_req.svg", "İstek başına CPU süresi (ms, düşük iyi)",
                      "Uygulama konteynerinin harcadığı CPU süresi / tamamlanan istek sayısı", cats, stacks,
                      val("app_cpu_ms_per_req"), lambda v: f"{fnum(v, 3)} ms")

    if has_srv_time(s, stacks, cats):
        grouped_hbars(CHARTS / "data_wait.svg", "İstek başına veri bekleme süresi (ms, düşük iyi)",
                      "Sunucunun ölçtüğü: veri deposuna gönderilmesinden sonuçların okunup çözülmesine kadar", cats, stacks,
                      val("srv_data_ms"), lambda v: f"{fnum(v, 3)} ms")

    L = []
    ap = L.append
    ap("### Genel ölçümler\n")
    ap("| Metrik | " + " | ".join(NAMES[k] for k in stacks) + " |")
    ap("|---|" + "---:|" * len(stacks))
    rows = [("Soğuk başlangıç (konteyner → /health 200), sn", "startup_s", 2),
            ("İlk istek gecikmesi (ms)", "first_request_ms", 0),
            ("İkinci istek gecikmesi (ms)", "second_request_ms", 1),
            ("Boşta bellek (MiB)", "idle_mem_mib", 0),
            ("Isınma sonrası bellek (MiB)", "after_warmup_mem_mib", 0),
            ("Test boyunca en yüksek bellek (MiB)", "peak_mem_mib", 0),
            ("İmaj boyutu (MB)", "image_mb", 0)]
    for label, key, d in rows:
        ap(f"| {label} | " + " | ".join(fnum(s[k].get(key), d) for k in stacks) + " |")
    if "spring" in s and s["spring"].get("jvm_started_s"):
        ap(f"| Spring'in kendi bildirdiği açılış süresi (sn) | - | {fnum(s['spring']['jvm_started_s'], 2)} |")
    ap("")
    ap("### Throughput ve gecikme\n")
    ap("| Endpoint | Go rps | Spring rps | Go/Spring | Go p50 | Spring p50 | Go p95 | Spring p95 | Go p99 | Spring p99 |")
    ap("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for p in cats:
        g, sp = s["go"]["phases"][p], s["spring"]["phases"][p]
        ratio = g["rps"] / sp["rps"] if sp["rps"] else None
        ap(f"| {LABELS[p]} | {fnum(g['rps'])} | {fnum(sp['rps'])} | {fnum(ratio, 2)}x | {fnum(g['p50_ms'], 1)} | "
           f"{fnum(sp['p50_ms'], 1)} | {fnum(g['p95_ms'], 1)} | {fnum(sp['p95_ms'], 1)} | {fnum(g['p99_ms'], 1)} | {fnum(sp['p99_ms'], 1)} |")
    ap("\n_Gecikmeler ms cinsinden._\n")
    ap("### Kaynak kullanımı (yük altında)\n")
    ap("| Endpoint | Go CPU % | Spring CPU % | Go RAM MiB | Spring RAM MiB | Go RAM tepe | Spring RAM tepe | DB CPU % (Go turu) | DB CPU % (Spring turu) |")
    ap("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for p in cats:
        g, sp = s["go"]["phases"][p], s["spring"]["phases"][p]
        ap(f"| {LABELS[p]} | {fnum(g['cpu_avg'])} | {fnum(sp['cpu_avg'])} | {fnum(g['mem_avg_mib'])} | {fnum(sp['mem_avg_mib'])} | "
           f"{fnum(g['mem_max_mib'])} | {fnum(sp['mem_max_mib'])} | {fnum(g['db_cpu_avg'])} | {fnum(sp['db_cpu_avg'])} |")
    if has_srv_time(s, stacks, cats):
        ap("\n### Veri bekleme süresi ve uygulama içi süre (sunucu tarafı, istek başına ortalama ms)\n")
        ap("| Endpoint | Go veri ms | Go uygulama ms | Go veri % | Spring veri ms | Spring uygulama ms | Spring veri % |")
        ap("|---|---:|---:|---:|---:|---:|---:|")
        for p in cats:
            g, sp = s["go"]["phases"][p], s["spring"]["phases"][p]
            row = [LABELS[p]]
            for x in (g, sp):
                d, t = x["srv_data_ms"], x["srv_total_ms"]
                app = (t - d) if (t is not None and d is not None) else None
                share = 100 * d / t if (t and d is not None) else None
                row += [fnum(d, 3), fnum(app, 3), fnum(share, 0)]
            ap("| " + " | ".join(row) + " |")
    if s.get("cold"):
        cg, cs = s["cold"]["go"], s["cold"]["spring"]
        ap(f"\n### Isınmasız tur ({cg['phase_seconds']} sn faz, ısınma yükü yok)\n")
        ap("| Endpoint | Go rps | Spring rps | Go/Spring | Go ısınmasız/ısınmalı | Spring ısınmasız/ısınmalı | Go p99 | Spring p99 |")
        ap("|---|---:|---:|---:|---:|---:|---:|---:|")
        for p in cats:
            if p in cg["phases"] and p in cs["phases"]:
                a_, b_ = cg["phases"][p], cs["phases"][p]
                wg, ws = s["go"]["phases"][p]["rps"], s["spring"]["phases"][p]["rps"]
                ap(f"| {LABELS[p]} | {fnum(a_['rps'])} | {fnum(b_['rps'])} | {fnum(a_['rps'] / b_['rps'], 2)}x | "
                   f"{fnum(a_['rps'] / wg, 2)}x | {fnum(b_['rps'] / ws, 2)}x | {fnum(a_['p99_ms'], 1)} | {fnum(b_['p99_ms'], 1)} |")
    if has_cpu_time(s, stacks, cats):
        ap("\n### CPU çalışma süresi (yük süresince harcanan toplam CPU)\n")
        ap("| Endpoint | Go CPU sn | Spring CPU sn | Go ms/istek | Spring ms/istek | Spring/Go | Veri deposu CPU sn (Go turu) | Veri deposu CPU sn (Spring turu) |")
        ap("|---|---:|---:|---:|---:|---:|---:|---:|")
        for p in cats:
            g, sp = s["go"]["phases"][p], s["spring"]["phases"][p]
            ratio = sp["app_cpu_ms_per_req"] / g["app_cpu_ms_per_req"] if g["app_cpu_ms_per_req"] else None
            ap(f"| {LABELS[p]} | {fnum(g['app_cpu_s'], 1)} | {fnum(sp['app_cpu_s'], 1)} | {fnum(g['app_cpu_ms_per_req'], 3)} | "
               f"{fnum(sp['app_cpu_ms_per_req'], 3)} | {fnum(ratio, 2)}x | {fnum(g['db_cpu_s'], 1)} | {fnum(sp['db_cpu_s'], 1)} |")
    ap("\n### Verimlilik: CPU başına throughput\n")
    ap("| Endpoint | Go rps / %CPU | Spring rps / %CPU |")
    ap("|---|---:|---:|")
    for p in cats:
        g, sp = s["go"]["phases"][p], s["spring"]["phases"][p]
        eg = g["rps"] / g["cpu_avg"] if g["cpu_avg"] else None
        es = sp["rps"] / sp["cpu_avg"] if sp["cpu_avg"] else None
        ap(f"| {LABELS[p]} | {fnum(eg, 1)} | {fnum(es, 1)} |")
    ap("\n### Hata oranı ve tur farkı\n")
    ap("| Endpoint | Go hata % | Spring hata % | Go rps (min–maks tur) | Spring rps (min–maks tur) |")
    ap("|---|---:|---:|---:|---:|")
    for p in cats:
        g, sp = s["go"]["phases"][p], s["spring"]["phases"][p]
        ap(f"| {LABELS[p]} | {fnum(g['error_rate'] * 100, 2)} | {fnum(sp['error_rate'] * 100, 2)} | "
           f"{fnum(g['rps_min'])}–{fnum(g['rps_max'])} | {fnum(sp['rps_min'])}–{fnum(sp['rps_max'])} |")
    (OUT / "tables.md").write_text("\n".join(L), encoding="utf-8")
    print("yazildi:", OUT / "summary.json", OUT / "tables.md", CHARTS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
