#!/usr/bin/env python3
"""Her endpoint'in hangi indeksi kullandığını PostgreSQL istatistik görünümlerinden (pg_stat_*) doğrular.

Her endpoint için: istatistik anlık görüntüsü -> kısa k6 yükü -> anlık görüntü -> fark.
Çıktı: results/index_check.json + konsola tablo. Performans ölçümü DEĞİLDİR (kısa, düşük eşzamanlılık).
"""
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench  # noqa: E402

ROOT = bench.ROOT
TMP = bench.RESULTS / "idxcheck_tmp"
bench.RAW = TMP  # k6 çıktıları geçici klasöre gitsin, results/raw'a karışmasın


def q(db, sql):
    r = bench.run(["docker", "exec", "bench-db", "psql", "-U", "postgres", "-d", db, "-tAF", "|", "-c", sql])
    return [line.split("|") for line in r.stdout.strip().splitlines() if line.strip()]


def snapshot():
    idx = {r[0]: int(r[1]) for r in q("bench", "SELECT indexrelname, idx_scan FROM pg_stat_user_indexes")}
    tab = {r[0]: {"seq_scan": int(r[1]), "seq_tup_read": int(r[2]), "upd": int(r[3]), "hot": int(r[4])}
           for r in q("bench", "SELECT relname, seq_scan, seq_tup_read, n_tup_upd, n_tup_hot_upd FROM pg_stat_user_tables")}
    return idx, tab


def main():
    TMP.mkdir(parents=True, exist_ok=True)
    s = bench.STACKS["go"]
    bench.run(["docker", "rm", "-f", "bench-go", "bench-spring"], check=False)
    bench.run(["docker", "exec", "bench-db", "psql", "-U", "postgres", "-c", "DROP DATABASE IF EXISTS bench WITH (FORCE)",
               "-c", "CREATE DATABASE bench TEMPLATE bench_tpl"])
    bench.run(["docker", "compose", "-f", str(ROOT / "compose.yaml"), "--profile", s["profile"], "up", "-d", s["service"]])
    if not bench.wait_health(s["internal"]):
        raise RuntimeError("go api saglikli olmadi")
    bench.psql("bench", "INSERT INTO items (id, name, category, price_cents, stock) "
                        "SELECT 10000000 + g, md5('d' || g), 'disposable', 100, 1 FROM generate_series(1, 60000) g")
    bench.psql("bench", "VACUUM (FREEZE, ANALYZE) items")
    # ısınma: bağlantı havuzu ve istatistik gürültüsü için
    bench.run_k6(s["internal"], "get", "idxcheck-warm", 8, 2)
    time.sleep(12)

    out = {}
    print(f"{'endpoint':<9} {'istek':>7}  {'kullanilan indeksler (tarama sayisi)':<58} {'seq scan':>8}  {'HOT güncelleme'}")
    for ph in bench.PHASES:
        i0, t0 = snapshot()
        path = bench.run_k6(s["internal"], ph, f"idxcheck-{ph}", 8, 3)
        # Boşta kalan bağlantılar pg_stat sayaçlarını ~10 sn gecikmeyle yazar; beklemezsek sayılar bir sonraki faza kayar.
        time.sleep(12)
        i1, t1 = snapshot()
        reqs = int(bench.read_k6(path)["count"])
        used = {k: i1[k] - i0.get(k, 0) for k in i1 if i1[k] - i0.get(k, 0) > 0}
        seq = t1["items"]["seq_scan"] - t0["items"]["seq_scan"]
        seq_rows = t1["items"]["seq_tup_read"] - t0["items"]["seq_tup_read"]
        upd = t1["items"]["upd"] - t0["items"]["upd"]
        hot = t1["items"]["hot"] - t0["items"]["hot"]
        hot_txt = f"{hot}/{upd} ({hot / upd * 100:.0f}%)" if upd else "-"
        out[ph] = {"requests": reqs, "index_scans": used, "items_seq_scans": seq, "items_seq_rows_read": seq_rows,
                   "updates": upd, "hot_updates": hot}
        used_txt = ", ".join(f"{k}:{v}" for k, v in used.items()) or "(indeks yok)"
        print(f"{ph:<9} {reqs:>7}  {used_txt:<58} {seq:>8}  {hot_txt}")

    # kullanılmayan indeksler + boyutlar
    sizes = q("bench", "SELECT indexrelname, pg_relation_size(indexrelid), idx_scan FROM pg_stat_user_indexes ORDER BY 1")
    print("\nindeks boyutlari / toplam tarama:")
    for name, size, scans in sizes:
        print(f"  {name:<28} {int(size) / 1024:8.0f} KiB   {scans} tarama")
    out["_indexes"] = [{"name": a, "bytes": int(b), "scans": int(c)} for a, b, c in sizes]
    vis = q("bench", "SELECT relallvisible, relpages FROM pg_class WHERE relname='items'")
    out["_visibility_map"] = {"all_visible_pages": int(vis[0][0]), "pages": int(vis[0][1])}
    print(f"\nitems: {vis[0][0]} / {vis[0][1]} sayfa 'all-visible' (index-only scan icin onemli)")

    (bench.RESULTS).mkdir(exist_ok=True)
    (bench.RESULTS / "index_check.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    bench.run(["docker", "rm", "-f", s["container"]], check=False)
    shutil.rmtree(TMP, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
