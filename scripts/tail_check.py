#!/usr/bin/env python3
"""Spring'in p95/p99 gecikme kuyruğu: konteyner CPU kotası (CFS throttling) mı?

Her yığın için GET /items/{id} yükü altında, aynı çalışan konteynerde:
  1) 2 CPU limitiyle ölç  2) `docker update --cpus 4` ile ölç
ve cgroup cpu.stat sayaçlarının (nr_periods, nr_throttled, throttled_usec) farkını al.
Sonuç: results/tail_check.json
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench  # noqa: E402

ROOT = bench.ROOT
TMP = bench.RESULTS / "tail_tmp"
bench.RAW = TMP


def cpu_stat(container):
    cid = bench.run(["docker", "inspect", "-f", "{{.Id}}", container]).stdout.strip()
    cmd = f"cat $(find /cg -name cpu.stat | grep {cid} | head -1)"
    r = bench.run(["docker", "run", "--rm", "-v", "/sys/fs/cgroup:/cg:ro", "alpine", "sh", "-c", cmd], check=False)
    d = {}
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            d[parts[0]] = int(parts[1])
    return d


def measure(stack, cpus, secs=20):
    s = bench.STACKS[stack]
    bench.run(["docker", "update", "--cpus", str(cpus), s["container"]])
    time.sleep(2)
    before = cpu_stat(s["container"])
    path = bench.run_k6(s["internal"], "get", f"{stack}-{cpus}", 64, secs)
    after = cpu_stat(s["container"])
    k = bench.read_k6(path)
    d = {key: after.get(key, 0) - before.get(key, 0) for key in ("nr_periods", "nr_throttled", "throttled_usec", "usage_usec")}
    k["cpus"] = cpus
    k["periods"] = d["nr_periods"]
    k["throttled_periods"] = d["nr_throttled"]
    k["throttled_pct"] = 100 * d["nr_throttled"] / d["nr_periods"] if d["nr_periods"] else None
    k["throttled_ms_per_s"] = d["throttled_usec"] / 1000 / secs
    return k


def main():
    TMP.mkdir(parents=True, exist_ok=True)
    out = {}
    for stack in ("go", "spring"):
        s = bench.STACKS[stack]
        bench.run(["docker", "rm", "-f", "bench-go", "bench-spring"], check=False)
        bench.run(["docker", "exec", "bench-db", "psql", "-U", "postgres", "-c", "DROP DATABASE IF EXISTS bench WITH (FORCE)",
                   "-c", "CREATE DATABASE bench TEMPLATE bench_tpl"])
        bench.run(["docker", "compose", "-f", str(ROOT / "compose.yaml"), "--profile", s["profile"], "up", "-d", s["service"]])
        assert bench.wait_health(s["internal"])
        print(f"== {stack}: isinma 45 sn ==", flush=True)
        bench.run_k6(s["internal"], "mixed", f"{stack}-warm", 64, 45)
        time.sleep(3)
        out[stack] = []
        for cpus in (2, 4, 2):  # son 2: ilk 2 ile aynı mı (tekrarlanabilirlik kontrolü)
            k = measure(stack, cpus)
            out[stack].append(k)
            print(f"  {cpus} CPU: {k['rps']:7.0f} rps | p50 {k['p50_ms']:6.2f} p95 {k['p95_ms']:6.2f} p99 {k['p99_ms']:6.2f} ms | "
                  f"kisitlanan dönem %{k['throttled_pct'] if k['throttled_pct'] is not None else float('nan'):.1f} "
                  f"| throttle {k['throttled_ms_per_s']:.0f} ms/sn", flush=True)
            time.sleep(3)
        bench.run(["docker", "rm", "-f", s["container"]], check=False)
    (bench.RESULTS / "tail_check.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
