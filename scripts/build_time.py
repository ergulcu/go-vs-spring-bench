#!/usr/bin/env python3
"""İki API imajının build süresini ölçer (Docker build).

  temiz build   : --no-cache; bağımlılık indirme (Go modülleri / Maven) dahil. Taban imajlar yerelde hazır, bunların çekilmesi dahil değil.
  artımlı build : yalnızca kaynak koda küçük bir değişiklik; bağımlılık katmanı önbellekten gelir (günlük geliştirme senaryosu).
Sonuç: results/raw/build_times.json

Not: yük testi sürerken çalıştırma; build CPU'yu yoğun kullanır ve ölçümü bozar.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = Path(os.environ.get("BENCH_RESULTS") or ROOT / "results")
RAW = RESULTS / "raw"
TARGETS = {
    "go": {"service": "go-api", "profile": "go", "file": ROOT / "go-api" / "main.go", "comment": "\n// build-time probe %d\n"},
    "spring": {"service": "spring-api", "profile": "spring",
               "file": ROOT / "spring-api" / "src" / "main" / "java" / "bench" / "ApiController.java",
               "comment": "\n// build-time probe %d\n"},
}


def build(t, no_cache):
    cmd = ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "--profile", t["profile"], "build"]
    if no_cache:
        cmd.append("--no-cache")
    cmd.append(t["service"])
    for attempt in (1, 2, 3):  # ağ kopmalarında yeniden dene; yalnızca başarılı denemenin süresi kaydedilir
        start = time.perf_counter()
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        dt = time.perf_counter() - start
        if r.returncode == 0:
            return dt
        print(f"    deneme {attempt} basarisiz, tekrar...", flush=True)
    raise RuntimeError("build 3 denemede de basarisiz")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--only", default="", help="yalnızca bu yığını yeniden ölç (go|spring); öncekiyle birleştirir")
    args = ap.parse_args()
    result = {}
    prev = RAW / "build_times.json"
    if args.only and prev.exists():
        result = json.loads(prev.read_text(encoding="utf-8"))
    for name, t in TARGETS.items():
        if args.only and name != args.only:
            continue
        print(f"== {name} ==", flush=True)
        clean, inc = [], []
        for i in range(args.reps):
            clean.append(build(t, no_cache=True))
            print(f"  temiz {i + 1}: {clean[-1]:.1f} sn", flush=True)
        original = t["file"].read_text(encoding="utf-8")
        try:
            build(t, no_cache=False)  # önbelleği güncel hale getir
            for i in range(args.reps):
                t["file"].write_text(original + t["comment"] % (i + 1), encoding="utf-8")
                inc.append(build(t, no_cache=False))
                print(f"  artimli {i + 1}: {inc[-1]:.1f} sn", flush=True)
        finally:
            t["file"].write_text(original, encoding="utf-8")  # kaynağı her durumda eski haline getir
        result[name] = {"clean_s": clean, "incremental_s": inc,
                        "clean_median_s": statistics.median(clean), "incremental_median_s": statistics.median(inc)}
    # değişen kaynağı geri aldık; imajları orijinal koddan yeniden oluştur (önbellekten hızlıca)
    for t in TARGETS.values():
        build(t, no_cache=False)
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "build_times.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("yazildi:", RAW / "build_times.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
