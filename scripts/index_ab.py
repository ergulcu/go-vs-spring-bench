#!/usr/bin/env python3
"""İndeks tasarımı A/B: kapsayan indeks (cover) vs sade indeks + fillfactor=80 (HOT güncellemeye yer açar).
Yalnızca Go API ile, /stats, PUT ve /orders için; varyantlar dönüşümlü koşulur. Karar için yön gösterir, ana ölçüm değildir."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench  # noqa: E402

ROOT = bench.ROOT
TMP = bench.RESULTS / "idxab_tmp"
bench.RAW = TMP

VARIANTS = {
    "cover": [],
    "plain_ff80": [
        "DROP INDEX items_category_cover_idx",
        "CREATE INDEX items_category_idx ON items (category)",
        "ALTER TABLE items SET (fillfactor = 80)",
        "VACUUM FULL items",
        "VACUUM (FREEZE, ANALYZE) items",
    ],
}
PHASES = ["stats", "update", "order"]
REPS = 2


def one(variant, rep):
    s = bench.STACKS["go"]
    bench.run(["docker", "rm", "-f", "bench-go"], check=False)
    bench.run(["docker", "exec", "bench-db", "psql", "-U", "postgres", "-c", "DROP DATABASE IF EXISTS bench WITH (FORCE)",
               "-c", "CREATE DATABASE bench TEMPLATE bench_tpl"])
    for sql in VARIANTS[variant]:
        bench.psql("bench", sql)
    bench.psql("bench", "SELECT pg_stat_reset()")
    bench.run(["docker", "compose", "-f", str(ROOT / "compose.yaml"), "--profile", "go", "up", "-d", s["service"]])
    assert bench.wait_health(s["internal"])
    bench.run_k6(s["internal"], "mixed", f"{variant}-{rep}-warm", 64, 15)
    res = {}
    for ph in PHASES:
        path = bench.run_k6(s["internal"], ph, f"{variant}-{rep}-{ph}", 64, 10)
        k = bench.read_k6(path)
        res[ph] = {"rps": k["rps"], "p99_ms": k["p99_ms"]}
        time.sleep(2)
    time.sleep(12)
    r = bench.run(["docker", "exec", "bench-db", "psql", "-U", "postgres", "-d", "bench", "-tAF", "|", "-c",
                   "SELECT n_tup_upd, n_tup_hot_upd FROM pg_stat_user_tables WHERE relname='items'"]).stdout.strip().split("|")
    res["hot_pct"] = 100 * int(r[1]) / int(r[0]) if int(r[0]) else 0
    bench.run(["docker", "rm", "-f", "bench-go"], check=False)
    return res


def main():
    TMP.mkdir(parents=True, exist_ok=True)
    runs = {v: [] for v in VARIANTS}
    for rep in range(REPS):
        for v in VARIANTS:  # dönüşümlü: cover, plain, cover, plain
            r = one(v, rep)
            runs[v].append(r)
            print(f"{v:<11} tekrar {rep + 1}: stats {r['stats']['rps']:6.0f} rps | update {r['update']['rps']:7.0f} rps | "
                  f"order {r['order']['rps']:6.0f} rps | HOT {r['hot_pct']:.0f}%", flush=True)
    print("\nOrtalama:")
    summ = {}
    for v, rs in runs.items():
        m = {ph: sum(r[ph]["rps"] for r in rs) / len(rs) for ph in PHASES}
        m["hot_pct"] = sum(r["hot_pct"] for r in rs) / len(rs)
        summ[v] = m
        print(f"  {v:<11} stats {m['stats']:6.0f} | update {m['update']:7.0f} | order {m['order']:6.0f} | HOT %{m['hot_pct']:.0f}")
    base = summ["cover"]
    print("\nplain_ff80 / cover:", {ph: round(summ['plain_ff80'][ph] / base[ph], 2) for ph in PHASES})
    (bench.RESULTS / "index_ab.json").write_text(json.dumps({"runs": runs, "mean": summ}, indent=2), encoding="utf-8")
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
