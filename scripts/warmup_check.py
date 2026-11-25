#!/usr/bin/env python3
"""Isınma süresi duyarlılığı: Spring (JIT) 45 sn mi, 180 sn mi ısınınca farklı throughput veriyor?
Ana testteki ısınma (45 sn) yeterli miydi? Sonuç: results/warmup_check.json"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench  # noqa: E402

ROOT = bench.ROOT
TMP = bench.RESULTS / "warm_tmp"
bench.RAW = TMP


def trial(stack, warm_s):
    s = bench.STACKS[stack]
    bench.run(["docker", "rm", "-f", "bench-go", "bench-spring"], check=False)
    bench.run(["docker", "exec", "bench-db", "psql", "-U", "postgres", "-c", "DROP DATABASE IF EXISTS bench WITH (FORCE)",
               "-c", "CREATE DATABASE bench TEMPLATE bench_tpl"])
    bench.run(["docker", "compose", "-f", str(ROOT / "compose.yaml"), "--profile", s["profile"], "up", "-d", s["service"]])
    assert bench.wait_health(s["internal"])
    bench.run_k6(s["internal"], "mixed", f"{stack}-{warm_s}-warm", 64, warm_s)
    time.sleep(3)
    res = {}
    for ph in ("health", "get", "health"):  # sondaki health: aynı fazın tekrarında fark var mı
        k = bench.read_k6(bench.run_k6(s["internal"], ph, f"{stack}-{warm_s}-{ph}-{len(res)}", 64, 20))
        res.setdefault(ph, []).append({"rps": k["rps"], "p99_ms": k["p99_ms"]})
        time.sleep(3)
    bench.run(["docker", "rm", "-f", s["container"]], check=False)
    return res


def main():
    TMP.mkdir(parents=True, exist_ok=True)
    out = {}
    for stack, warm in (("spring", 45), ("spring", 180), ("go", 45), ("go", 180)):
        r = trial(stack, warm)
        out[f"{stack}-{warm}"] = r
        print(f"{stack:<6} isinma {warm:>3} sn | health ilk {r['health'][0]['rps']:7.0f}  get {r['get'][0]['rps']:7.0f}  health son {r['health'][1]['rps']:7.0f} rps", flush=True)
    (bench.RESULTS / "warmup_check.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
