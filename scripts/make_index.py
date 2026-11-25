#!/usr/bin/env python3
"""results/ altındaki senaryo klasörlerinden (her birinde summary.json) karşılaştırmalı bir özet sayfası üretir: results/index.html"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_html as rh  # noqa: E402

n, esc, table, PHASES, LABELS = rh.n, rh.esc, rh.table, rh.PHASES, rh.LABELS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    a = ap.parse_args()
    root = Path(a.results)
    sc = []
    for d in sorted(root.iterdir()):
        if d.name.startswith("_") or not (d / "summary.json").exists():
            continue
        meta = json.loads((d / "scenario.json").read_text(encoding="utf-8")) if (d / "scenario.json").exists() else {}
        sc.append((d.name, meta, json.loads((d / "summary.json").read_text(encoding="utf-8"))))
    sc.sort(key=lambda x: (-x[1].get("app_cpus", 0), x[1].get("store", "postgres") != "postgres"))
    if not sc:
        print("sonuç bulunamadı")
        return 1

    heads = ["Endpoint"]
    for name, meta, _ in sc:
        t = meta.get("name", name)
        heads += [f"{t}: Go rps", f"{t}: Spring rps", f"{t}: Go / Spring"]
    rows = []
    for p in PHASES:
        row = [LABELS[p]]
        for _, _, s in sc:
            g, sp = s["go"]["phases"].get(p), s["spring"]["phases"].get(p)
            row += [n(g["rps"]), n(sp["rps"]), f"{n(g['rps'] / sp['rps'], 2)}x"] if g and sp else ["-", "-", "-"]
        rows.append(row)
    t_thr = table(heads, rows)

    heads2 = ["Metrik"]
    for name, meta, _ in sc:
        t = meta.get("name", name)
        heads2 += [f"{t}: Go", f"{t}: Spring"]

    def avg(s, k, m):
        ph = s[k]["phases"]
        return sum(v[m] for v in ph.values()) / len(ph)

    def err(s, k):
        ph = s[k]["phases"]
        return max(v["error_rate"] for v in ph.values()) * 100
    rows2 = []
    for label, fn, d in [("Ortalama bellek (yük altında), MiB", lambda s, k: avg(s, k, "mem_avg_mib"), 0),
                         ("Ortalama p99 gecikme, ms", lambda s, k: avg(s, k, "p99_ms"), 1),
                         ("Soğuk başlangıç, sn", lambda s, k: s[k]["startup_s"], 1),
                         ("İlk istek gecikmesi, ms", lambda s, k: s[k]["first_request_ms"], 0),
                         ("En yüksek endpoint hata oranı, %", err, 2)]:
        row = [label]
        for _, _, s in sc:
            row += [n(fn(s, "go"), d), n(fn(s, "spring"), d)]
        rows2.append(row)
    t_gen = table(heads2, rows2)

    links = "".join(f"<li><a href='{esc(name)}/report.html'>{esc(meta.get('name', name))}: ayrıntılı rapor</a></li>" for name, meta, _ in sc)
    html = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Go vs Spring Boot - senaryo özeti</title><style>{rh.CSS}</style></head><body><div class="wrap">
<h1>Go vs Spring Boot: limit senaryoları</h1>
<p class="sub">Aynı kod; senaryolar uygulama konteynerinin CPU/RAM limitini ve veri deposunu (PostgreSQL ya da bellek içi Valkey) değiştirir.</p>
<ul class="find">{links}</ul>
<h2>Throughput</h2>{t_thr}
<h2>Bellek, gecikme, başlangıç</h2>{t_gen}
<p class="muted">Hata oranı sıfırdan büyükse (özellikle küçük limitte) uygulama yükü kaldıramamış demektir: o senaryodaki rps değerleri başarılı istekleri değil, tüm istekleri sayar. Ayrıntı için ilgili raporun "Hata oranı" tablosuna bakın.</p>
</div></body></html>"""
    (root / "index.html").write_text(html, encoding="utf-8")
    print("yazildi:", root / "index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
