#!/usr/bin/env python3
"""Tek komutla tam koşu (runner konteynerinin giriş noktası):

    docker compose run --rm runner              # tam koşu: PostgreSQL ve Valkey × 1 CPU/1 GiB ve 0,5 CPU/512 MiB (4 senaryo)
    docker compose run --rm runner --quick      # kısa deneme koşusu
    docker compose run --rm runner --limits 1:1g          # yalnızca tek limit
    docker compose run --rm runner --limits 2:2g,0.5:512m  # istediğiniz limitler (cpu:bellek)
    docker compose run --rm runner --stores postgres        # yalnızca PostgreSQL
    docker compose run --rm runner --stores valkey          # yalnızca bellek içi veri deposu (Valkey)

Adımlar: ön kontrol -> imajları build et -> (isteğe bağlı) build süresi ölçümü -> her limit senaryosu için
veritabanını sıfırdan kur + bench.py -> rapor (results/<senaryo>/report.html) -> results/index.html -> konteynerleri temizle.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
COMPOSE = ["docker", "compose", "-f", str(ROOT / "compose.yaml")]
PY = [sys.executable, "-u"]
VALKEY_FLAGS = ("4 GiB, bellek içi, kalıcılık kapalı (save \"\", appendonly no), io-threads 4; "
                "komutlar tek iş parçacığında yürür, yazmalar Lua betiğiyle tek turda")
DB_FLAGS = ("4 GiB, shared_buffers=1GB, fsync=off, synchronous_commit=off, full_page_writes=off, jit=off, "
            "paralel sorgu işçisi 4; yalnızca items_pkey + lower(name) indeksi, fillfactor=80")


def sh(cmd, check=True, retries=1, env=None):
    """Çıktısını canlı gösteren komut; ağ kopmalarına karşı yeniden dener."""
    for attempt in range(1, retries + 1):
        r = subprocess.run(cmd, env=env)
        if r.returncode == 0 or not check:
            return r.returncode
        if attempt < retries:
            print(f"  deneme {attempt} başarısız, 5 sn sonra tekrar...", flush=True)
            time.sleep(5)
    raise SystemExit(f"komut başarısız: {' '.join(map(str, cmd))}")


def out(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()


def parse_limit(spec):
    cpus, mem = spec.split(":")
    mem_mib = float(mem[:-1]) * (1024 if mem[-1].lower() == "g" else 1)
    mem_txt = f"{mem[:-1]} GiB" if mem[-1].lower() == "g" else f"{mem[:-1]} MiB"
    name = f"{cpus}cpu-{mem.lower()}"
    return {"name": name, "cpus": cpus, "mem": mem.lower(), "mem_txt": mem_txt, "mem_mib": int(mem_mib)}


def preflight():
    info = out(["docker", "info", "--format", "{{.NCPU}}|{{.MemTotal}}"]).split("|")
    if len(info) != 2:
        raise SystemExit("Docker'a erişilemedi. Docker Desktop çalışıyor mu? (runner için /var/run/docker.sock gerekir)")
    ncpu, mem_gib = int(info[0]), int(info[1]) / 2**30
    print(f"Docker'ın görebildiği kaynak: {ncpu} CPU, {mem_gib:.1f} GiB RAM", flush=True)
    if not os.environ.get("DB_CPUS"):
        os.environ["DB_CPUS"] = str(min(8, ncpu))
    if ncpu < 8:
        print(f"UYARI: yalnızca {ncpu} CPU var; veritabanı limiti {os.environ['DB_CPUS']} CPU'ya düşürüldü. "
              "Uygulama, veritabanı ve k6 aynı çekirdekler için yarışır; sonuçlar referanstan belirgin sapabilir.", flush=True)
    if mem_gib < 6.5:
        print("UYARI: Docker'a 6,5 GiB'den az RAM verilmiş; veritabanı (4 GiB) + uygulama (2 GiB) limitleri sığmayabilir. "
              "Docker Desktop > Settings > Resources'tan artırın.", flush=True)
    return ncpu, mem_gib


def archive_previous():
    if not RESULTS.exists() or not any(RESULTS.iterdir()):
        return
    prev = RESULTS / "_previous"
    stash = ROOT / ".results_stash"
    shutil.rmtree(stash, ignore_errors=True)
    stash.mkdir()
    for p in list(RESULTS.iterdir()):
        if p.name != "_previous":
            shutil.move(str(p), str(stash / p.name))
    shutil.rmtree(prev, ignore_errors=True)
    prev.mkdir(parents=True)
    for p in list(stash.iterdir()):
        shutil.move(str(p), str(prev / p.name))
    shutil.rmtree(stash, ignore_errors=True)
    print("Önceki sonuçlar results/_previous/ klasörüne taşındı.", flush=True)


def cleanup():
    subprocess.run(["docker", "rm", "-f", "-v", "bench-db", "bench-valkey", "bench-go", "bench-spring"], capture_output=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="kısa deneme: 1 tur, 30 sn ısınma, 10 sn/endpoint, build süresi ölçülmez")
    ap.add_argument("--limits", default="1:1g,0.5:512m", help="uygulama limitleri, cpu:bellek listesi (varsayılan: 1:1g,0.5:512m)")
    ap.add_argument("--rounds", type=int)
    ap.add_argument("--warmup", type=int)
    ap.add_argument("--phase-seconds", type=int)
    ap.add_argument("--vus", type=int, default=64)
    ap.add_argument("--stores", default="postgres,valkey", help="veri deposu senaryoları: postgres, valkey ya da postgres,valkey (varsayılan: postgres,valkey)")
    ap.add_argument("--build-times", action="store_true", help="build süresini de ölç (tam koşuda varsayılan açık)")
    ap.add_argument("--no-build-times", action="store_true")
    ap.add_argument("--cold-round", action="store_true", help="ısınmasız (60 sn fazlı) tur ekle (tam koşuda varsayılan açık)")
    ap.add_argument("--no-cold-round", action="store_true")
    ap.add_argument("--extras", action="store_true", help="ek doğrulamalar: CPU kotası (tail_check) ve indeks (index_check); yalnızca 2 CPU senaryosunda")
    args = ap.parse_args()
    rounds = args.rounds or (1 if args.quick else 3)
    warmup = args.warmup or (30 if args.quick else 180)
    phase_s = args.phase_seconds or (10 if args.quick else 20)
    do_build_times = args.build_times or (not args.quick and not args.no_build_times)
    cold_round = args.cold_round or (not args.quick and not args.no_cold_round)
    limits = [parse_limit(x) for x in args.limits.split(",")]
    stores = [x.strip() for x in args.stores.split(",") if x.strip()]
    if not stores or any(x not in ("postgres", "valkey") for x in stores):
        raise SystemExit("--stores yalnızca postgres ve/veya valkey olabilir")

    ncpu, mem_gib = preflight()
    archive_previous()
    RESULTS.mkdir(exist_ok=True)
    t_start = time.time()
    done = []
    try:
        cleanup()
        print("\n== İmajlar build ediliyor (ilk seferde Maven/Go bağımlılıkları iner, birkaç dakika sürer) ==", flush=True)
        sh(COMPOSE + ["--profile", "go", "--profile", "spring", "--progress", "plain", "build"], retries=3)

        shared = RESULTS / "_shared"
        if do_build_times:
            print("\n== Build süreleri ölçülüyor ==", flush=True)
            env = dict(os.environ, BENCH_RESULTS=str(shared))
            sh(PY + [str(ROOT / "scripts" / "build_time.py")], env=env)

        for store in stores:
            for lim in limits:
                label = f"{lim['cpus']} CPU / {lim['mem_txt']}"
                name = lim["name"] if store == "postgres" else f"valkey-{lim['name']}"
                d = RESULTS / name
                print("", flush=True)
                print(f"######## Senaryo: {'PostgreSQL' if store == 'postgres' else 'Valkey'}, uygulama başına {label} ########", flush=True)
                os.environ["APP_CPUS"], os.environ["APP_MEM"], os.environ["STORE"] = lim["cpus"], lim["mem"], store
                env = dict(os.environ, BENCH_RESULTS=str(d))
                cleanup()  # her senaryo veri deposunu sıfırdan kurar
                if store == "postgres":
                    print("Veritabanı kuruluyor (100.000 satır tohum veri)...", flush=True)
                    sh(COMPOSE + ["up", "-d", "--wait", "db"], retries=2)
                else:
                    print("Valkey başlatılıyor (tohum veri her turda bench.py tarafından yüklenir)...", flush=True)
                    sh(COMPOSE + ["up", "-d", "--wait", "valkey"], retries=2)
                (d / "raw").mkdir(parents=True, exist_ok=True)
                if (shared / "raw" / "build_times.json").exists():
                    shutil.copy(shared / "raw" / "build_times.json", d / "raw" / "build_times.json")
                sh(PY + [str(ROOT / "scripts" / "bench.py"), "--rounds", str(rounds), "--warmup", str(warmup),
                         "--phase-seconds", str(phase_s), "--vus", str(args.vus)] + (["--cold-round"] if cold_round else []), env=env)
                if args.extras and store == "postgres" and lim["cpus"] == "2":
                    for s_ in ("tail_check.py", "index_check.py"):
                        sh(PY + [str(ROOT / "scripts" / s_)], env=env, check=False)
                host = json.loads((d / "raw" / "versions.json").read_text(encoding="utf-8")).get("host", "")
                meta = {"name": label if store == "postgres" else f"Valkey · {label}", "short": name, "store": store,
                        "db": f"{os.environ['DB_CPUS']} CPU, " + (DB_FLAGS if store == "postgres" else VALKEY_FLAGS),
                        "hardware": host or "kaydedilmedi", "app_cpus": float(lim["cpus"]),
                        "app_mem": lim["mem_txt"], "app_mem_mib": lim["mem_mib"]}
                (d / "scenario.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
                sh(PY + [str(ROOT / "scripts" / "report_html.py"), "--dir", str(d)], check=False)
                done.append({**lim, "name": name})
                cleanup()
    finally:
        cleanup()

    shutil.rmtree(RESULTS / "_shared", ignore_errors=True)
    if done:
        sh(PY + [str(ROOT / "scripts" / "make_index.py"), "--results", str(RESULTS)], check=False)
    mins = (time.time() - t_start) / 60
    print(f"\nBitti ({mins:.0f} dk). Raporlar:", flush=True)
    for lim in done:
        print(f"  results/{lim['name']}/report.html", flush=True)
    print("  results/index.html (senaryoların özeti)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
