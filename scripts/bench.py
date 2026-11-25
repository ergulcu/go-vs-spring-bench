#!/usr/bin/env python3
"""Go vs Spring Boot yük testi orkestratörü (her şey Docker'da).

Bu betik "runner" konteynerinin içinde çalışır (docker compose run --rm runner); Docker'ı /var/run/docker.sock üzerinden
kullanır, API konteynerlerine ve veritabanına Docker ağı içindeki adlarıyla (bench-go, bench-spring, bench-db) erişir.

Her tur için sırayla:
  1. "bench" veritabanı şablondan yeniden oluşturulur (iki taraf da aynı veriyle başlar)
  2. API konteyneri sıfırdan başlatılır (soğuk başlangıç ölçülür)
  3. Boşta bellek, ilk istek gecikmesi, ısınma (karışık yük)
  4. 14 endpoint sırayla k6 ile yüklenir; docker stats ile CPU/RAM örneklenir
Sonuçlar results/raw/ altına JSON olarak yazılır.
"""
import argparse
import calendar
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = Path(os.environ.get("BENCH_RESULTS") or ROOT / "results")
RAW = RESULTS / "raw"
NETWORK = "gobench_default"
K6_IMAGE = "grafana/k6:latest"
SELF = os.environ.get("HOSTNAME", "")  # konteynerin kimliği (docker varsayılanı); k6 bununla bağlama noktalarını devralır

STACKS = {
    "go": {"service": "go-api", "profile": "go", "container": "bench-go",
           "internal": "http://bench-go:8080", "image": "bench-go-api:latest"},
    "spring": {"service": "spring-api", "profile": "spring", "container": "bench-spring",
               "internal": "http://bench-spring:8080", "image": "bench-spring-api:latest"},
}
PHASES = ["health", "list", "get", "search", "stats", "cpu", "order", "create", "update", "delete", "report_store", "report_all", "b64", "fact"]
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
STORE = os.environ.get("STORE") or "postgres"  # postgres | valkey (bellek içi veri deposu senaryosu)
DATA_CONTAINER = "bench-valkey" if STORE == "valkey" else "bench-db"  # CPU'sı örneklenen veri deposu konteyneri
VALKEY_DEL_COUNT = int(os.environ.get("BENCH_VALKEY_DEL_COUNT", "2000000"))  # DELETE fazı için ayrılmış kayıt sayısı


def run(cmd, check=True, timeout=None):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"komut basarisiz: {' '.join(map(str, cmd))}\n{r.stdout}\n{r.stderr}")
    return r


def resp(*args):
    """Redis protokolü (RESP) komutu: valkey-cli --pipe ile toplu yüklemek için."""
    crlf = bytes([13, 10])
    parts = [b"*" + str(len(args)).encode() + crlf]
    for a in args:
        b = a if isinstance(a, bytes) else str(a).encode()
        parts.append(b"$" + str(len(b)).encode() + crlf + b + crlf)
    return b"".join(parts)


def seed_commands():
    """db/init.sql ile AYNI veri (deterministik): 100.000 ürün, 20 mağaza, 40.000 satış. Önce her şeyi siler."""
    yield resp("FLUSHALL")
    for g in range(1, 100001):
        name = hashlib.md5(str(g).encode()).hexdigest()
        yield resp("HSET", f"item:{g}", "name", name, "category", f"cat-{g % 20}", "price_cents", 100 + (g * 37) % 100000, "stock", 1000000)
        yield resp("ZADD", "items:ids", g, g)
        yield resp("ZADD", "items:names", 0, f"{name}:{g}")
    yield resp("SET", "items:seq", 100000)
    yield resp("SET", "orders:seq", 0)
    cities = ["Istanbul", "Ankara", "Izmir", "Bursa", "Antalya"]
    for g in range(1, 21):
        yield resp("HSET", f"store:{g}", "name", f"Store {g:02d}", "city", cities[g % 5])
        yield resp("ZADD", "stores:ids", g, g)
    base = calendar.timegm((2024, 1, 1, 0, 0, 0))
    for g in range(1, 40001):
        ts = base + ((g * 7919) % 731) * 86400 + (g * 104729) % 86400
        yield resp("RPUSH", f"sales:{1 + g % 20}", f"{ts}|{1 + g % 5}|{500 + (g * 37) % 20000}")


def delete_range_commands(count):
    """DELETE fazı için ayrılmış kayıtlar (PostgreSQL'deki 10.000.000+ aralığının karşılığı); yalnızca 'name' alanı yeter."""
    for g in range(1, count + 1):
        yield resp("HSET", f"item:{10000000 + g}", "name", f"d{g}")


def valkey_load(commands):
    p = subprocess.Popen(["docker", "exec", "-i", "bench-valkey", "valkey-cli", "--pipe"],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    buf, size = [], 0
    for c in commands:
        buf.append(c)
        size += len(c)
        if size > (1 << 20):
            p.stdin.write(b"".join(buf))
            buf, size = [], 0
    p.stdin.write(b"".join(buf))
    p.stdin.close()
    out = p.stdout.read().decode("utf-8", "replace")
    p.wait()
    if p.returncode != 0 or "errors: 0" not in out:
        raise RuntimeError("valkey yukleme basarisiz: " + out)


def valkey_reset():
    valkey_load(seed_commands())


def valkey_dbsize():
    return int(run(["docker", "exec", "bench-valkey", "valkey-cli", "dbsize"]).stdout.strip())


def psql(db, sql):
    return run(["docker", "exec", "bench-db", "psql", "-U", "postgres", "-d", db, "-v", "ON_ERROR_STOP=1", "-c", sql])


def scalar(db, sql):
    r = run(["docker", "exec", "bench-db", "psql", "-U", "postgres", "-d", db, "-tA", "-c", sql])
    return int(r.stdout.strip())


def to_mib(value, unit):
    unit = unit.lower()
    factor = {"b": 1 / 1048576, "kib": 1 / 1024, "kb": 1 / 1024, "mib": 1, "mb": 1, "gib": 1024, "gb": 1024}
    return value * factor.get(unit, 1)


class Sampler:
    """docker stats akışını (~1 Hz) okur: (zaman, cpu%, bellek MiB)."""

    def __init__(self, container):
        self.container = container
        self.samples = []
        self.proc = None
        self.thread = None

    def start(self):
        self.proc = subprocess.Popen(
            ["docker", "stats", "--format", "{{.CPUPerc}}|{{.MemUsage}}", self.container],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        for line in self.proc.stdout:
            line = ANSI.sub("", line).strip()
            m = re.match(r"([\d.]+)%\|([\d.]+)\s*([A-Za-z]+)", line)
            if m:
                self.samples.append((time.time(), float(m.group(1)), to_mib(float(m.group(2)), m.group(3))))

    def stop(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.thread:
            self.thread.join(timeout=5)

    def window(self, t_from, t_to):
        pts = [s for s in self.samples if t_from <= s[0] <= t_to]
        if not pts:
            return None
        cpu = [p[1] for p in pts]
        mem = [p[2] for p in pts]
        return {"n": len(pts), "cpu_avg": statistics.fmean(cpu), "cpu_max": max(cpu),
                "mem_avg_mib": statistics.fmean(mem), "mem_max_mib": max(mem)}


def wait_health(base_url, timeout=180):
    url = f"{base_url}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def http_ms(url):
    t = time.perf_counter()
    with urllib.request.urlopen(url, timeout=30) as r:
        r.read()
    return (time.perf_counter() - t) * 1000


def stats_once(container):
    r = run(["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}|{{.MemUsage}}", container])
    m = re.match(r"([\d.]+)%\|([\d.]+)\s*([A-Za-z]+)", ANSI.sub("", r.stdout).strip())
    return {"cpu": float(m.group(1)), "mem_mib": to_mib(float(m.group(2)), m.group(3))} if m else None


def cpu_usage_usec(containers):
    """Konteynerlerin harcadığı toplam CPU süresi (kullanıcı + çekirdek, mikrosaniye): cgroup v2 cpu.stat > usage_usec.
    Dönen sözlükte okunamayan konteyner yoktur (cgroup v1 ya da erişim yoksa boş döner)."""
    r = run(["docker", "inspect", "-f", "{{.Name}} {{.Id}}", *containers], check=False)
    pairs = [ln.split() for ln in r.stdout.splitlines() if len(ln.split()) == 2]
    if not pairs:
        return {}
    script = "; ".join(
        f'echo {name.lstrip("/")} $(grep usage_usec $(find /cg -name cpu.stat | grep {cid} | head -1) | cut -d" " -f2)'
        for name, cid in pairs)
    r = run(["docker", "run", "--rm", "-v", "/sys/fs/cgroup:/cg:ro", "alpine", "sh", "-c", script], check=False)
    out = {}
    for ln in r.stdout.splitlines():
        parts = ln.split()
        if len(parts) == 2 and parts[1].isdigit():
            out[parts[0]] = int(parts[1])
    return out


def cpu_time(before, after, app_name, data_name, requests):
    """İki okumanın farkından: uygulama ve veri deposunun CPU süresi (sn) ve istek başına CPU süresi (ms)."""
    res = {}
    for key, name in (("app", app_name), ("db", data_name)):
        if name in before and name in after and after[name] >= before[name]:
            sec = (after[name] - before[name]) / 1e6
            res[f"{key}_s"] = sec
            res[f"{key}_ms_per_req"] = sec * 1000 / requests if requests else None
    return res or None


def run_k6(target, endpoint, out, vus, duration_s):
    RAW.mkdir(parents=True, exist_ok=True)
    # k6'ya repo klasörünü runner konteynerinden devralarak veriyoruz (--volumes-from): ana makine yolu bilmemiz gerekmez.
    # --user root: Linux'ta bind mount edilmiş results/ klasörüne yazabilmesi için.
    cmd = ["docker", "run", "--rm", "--network", NETWORK, "--user", "root", "--volumes-from", SELF,
           "-e", f"TARGET={target}", "-e", f"ENDPOINT={endpoint}", "-e", f"VUS={vus}",
           "-e", f"DURATION={duration_s}s", "-e", f"OUT={out}", "-e", f"STORE={STORE}", "-e", f"RESULTS_DIR={RAW.as_posix()}",
           K6_IMAGE, "run", "--quiet", "--no-usage-report", (ROOT / "k6" / "test.js").as_posix()]
    run(cmd, timeout=duration_s + 120)
    return RAW / f"{out}.json"


def read_k6(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    m = d["metrics"]

    def vals(name):
        x = m.get(name, {})
        return x.get("values", x)

    dur, reqs, failed = vals("http_req_duration"), vals("http_reqs"), vals("http_req_failed")
    sd, st = vals("srv_data_ms"), vals("srv_total_ms")  # sunucunun kendi ölçtüğü süreler (Server-Timing)
    return {"rps": reqs.get("rate"), "count": reqs.get("count"),
            "srv_data_avg_ms": sd.get("avg"), "srv_data_p95_ms": sd.get("p(95)"),
            "srv_total_avg_ms": st.get("avg"), "srv_total_p95_ms": st.get("p(95)"),
            "avg_ms": dur.get("avg"), "p50_ms": dur.get("med"), "p90_ms": dur.get("p(90)"),
            "p95_ms": dur.get("p(95)"), "p99_ms": dur.get("p(99)"), "max_ms": dur.get("max"),
            "error_rate": failed.get("rate", failed.get("value", 0))}


def run_stack(name, rnd, args, cold=False):
    s = STACKS[name]
    tag = f"{'c' if cold else 'r'}{rnd}-{name}"  # c: ısınmasız tur (raporda ayrı bölüm), r: normal tur
    label = f" (ISINMASIZ, {args.phase_seconds} sn faz)" if cold else ""
    print(f"\n===== tur {rnd}{label} :: {name} =====", flush=True)

    run(["docker", "rm", "-f", "bench-go", "bench-spring"], check=False)
    if STORE == "valkey":
        valkey_reset()  # her tur taze başlar: FLUSHALL + aynı tohum veri
    else:
        run(["docker", "exec", "bench-db", "psql", "-U", "postgres", "-c", "DROP DATABASE IF EXISTS bench WITH (FORCE)",
             "-c", "CREATE DATABASE bench TEMPLATE bench_tpl"])
    time.sleep(2)

    # --- soğuk başlangıç ---
    t0 = time.time()
    run(["docker", "compose", "-f", str(ROOT / "compose.yaml"), "--profile", s["profile"], "up", "-d", s["service"]])
    if not wait_health(s["internal"]):
        raise RuntimeError(f"{name} saglikli olmadi")
    startup_s = time.time() - t0
    first_req_ms = http_ms(f"{s['internal']}/items/1")
    second_req_ms = http_ms(f"{s['internal']}/items/2")
    jvm_started = None
    if name == "spring":
        log = run(["docker", "logs", s["container"]], check=False)
        m = re.search(r"Started \w+ in ([\d.]+) seconds", log.stdout + log.stderr)
        jvm_started = float(m.group(1)) if m else None

    time.sleep(8)
    idle = stats_once(s["container"])
    print(f"  baslangic {startup_s:.2f}s | ilk istek {first_req_ms:.0f} ms | bosta {idle}", flush=True)

    if args.warmup > 0:
        # --- ısınma ---
        print(f"  isinma {args.warmup}s (karisik yuk)...", flush=True)
        run_k6(s["internal"], "mixed", f"{tag}-warmup", args.vus, args.warmup)
        time.sleep(5)
        # Isınma yazma yaptı: ölü satırlar ve eski istatistik kalır. Gerçek sistemlerde autovacuum bunu yapar;
        # testte iki yığına da aynı noktada ve aynı şekilde uygulanır (ölçümler temiz bir tablo durumundan başlar).
        # ADİLLİK: ısınmadaki POST /items tabloya satır ekler, hızlı yığın daha çok ekler (daha büyük tabloda ölçülür, /stats yavaşlar).
        # Isınma sonrası iki yığın için de tabloyu aynı 100.000 satırlık başlangıç durumuna döndür.
        if STORE == "valkey":
            # Valkey: ısınmanın eklediği/değiştirdiği her şey silinir, aynı tohum veri yeniden yüklenir (anahtar sayısı).
            rows_raw = valkey_dbsize()
            valkey_reset()
            rows_clean = valkey_dbsize()
        else:
            rows_raw = scalar("bench", "SELECT count(*) FROM items")
            psql("bench", "DELETE FROM items WHERE id > 100000 AND id < 10000000")
            psql("bench", "TRUNCATE orders")
            psql("bench", "VACUUM FULL items")
            psql("bench", "VACUUM (FREEZE, ANALYZE) items")
            rows_clean = scalar("bench", "SELECT count(*) FROM items")
        print(f"  isinma sonrasi {'anahtar' if STORE == 'valkey' else 'satir'}: {rows_raw} -> temizlik sonrasi {rows_clean}", flush=True)
        time.sleep(2)
        after_warmup = stats_once(s["container"])
    else:
        # Isınmasız tur: konteyner taze başlar, hiç ısınma yükü yoktur; fazlar doğrudan ölçülür.
        print("  isinma YOK (isinmasiz tur)", flush=True)
        rows_raw = rows_clean = None
        time.sleep(2)
        after_warmup = stats_once(s["container"])

    # --- endpoint fazları ---
    phases = {}
    for ph in PHASES:
        if args.phases and ph not in args.phases:
            continue
        if STORE == "valkey" and ph == "stats":
            continue  # SQL GROUP BY'ın bellek içi depoda doğal bir karşılığı yok
        if ph == "delete":
            if STORE == "valkey":
                valkey_load(delete_range_commands(max(VALKEY_DEL_COUNT, args.phase_seconds * 40000)))
            else:
                psql("bench", "INSERT INTO items (id, name, category, price_cents, stock) "
                              f"SELECT 10000000 + g, md5('d' || g), 'disposable', 100, 1 FROM generate_series(1, {max(800000, args.phase_seconds * 25000)}) g")
                psql("bench", "ANALYZE items")
        app, db = Sampler(s["container"]), Sampler(DATA_CONTAINER)
        app.start()
        db.start()
        time.sleep(1.5)
        out = f"{tag}-{ph}"
        conts = [s["container"], DATA_CONTAINER]
        cpu0 = cpu_usage_usec(conts)
        path = run_k6(s["internal"], ph, out, args.vus, args.phase_seconds)
        t_after = time.time()
        app.stop()
        db.stop()
        cpu1 = cpu_usage_usec(conts)
        w_from, w_to = t_after - args.phase_seconds - 0.1, t_after - 1.0
        k = read_k6(path)
        k["app"] = app.window(w_from, w_to)
        k["db"] = db.window(w_from, w_to)
        k["cpu_time"] = cpu_time(cpu0, cpu1, s["container"], DATA_CONTAINER, k["count"])
        phases[ph] = k
        a = k["app"] or {}
        print(f"  {ph:<7} {k['rps']:9.0f} rps | p50 {k['p50_ms']:7.2f} p95 {k['p95_ms']:7.2f} p99 {k['p99_ms']:7.2f} ms | "
              f"hata {k['error_rate']*100:.2f}% | app cpu {a.get('cpu_avg', 0):6.1f}% ram {a.get('mem_avg_mib', 0):6.0f} MiB | "
              f"db cpu {(k['db'] or {}).get('cpu_avg', 0):6.1f}%"
              + (f" | cpu süresi {k['cpu_time']['app_s']:6.1f} sn ({k['cpu_time']['app_ms_per_req']:.3f} ms/istek)"
                 if k.get("cpu_time") and k["cpu_time"].get("app_ms_per_req") is not None else ""), flush=True)
        time.sleep(3)

    size = run(["docker", "image", "inspect", s["image"], "--format", "{{.Size}}"]).stdout.strip()
    result = {"stack": name, "store": STORE, "round": rnd, "cold": cold, "startup_s": startup_s, "jvm_started_s": jvm_started,
              "first_request_ms": first_req_ms, "second_request_ms": second_req_ms,
              "idle": idle, "after_warmup": after_warmup, "image_bytes": int(size),
              "rows_after_warmup_raw": rows_raw, "rows_after_cleanup": rows_clean,
              "phases": phases, "vus": args.vus, "phase_seconds": args.phase_seconds, "warmup_seconds": args.warmup}
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"run-{tag}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    run(["docker", "rm", "-f", s["container"]], check=False)
    return result


def collect_versions():
    v = {}
    v["go"] = run(["docker", "run", "--rm", "golang:1.27-alpine", "go", "version"], check=False).stdout.strip()
    j = run(["docker", "run", "--rm", "eclipse-temurin:25-jre", "java", "-version"], check=False)
    v["java"] = (j.stderr or j.stdout).strip().splitlines()[0] if (j.stderr or j.stdout).strip() else ""
    if STORE == "valkey":
        v["valkey"] = run(["docker", "exec", "bench-valkey", "valkey-server", "--version"], check=False).stdout.strip()
    else:
        v["postgres"] = run(["docker", "exec", "bench-db", "postgres", "--version"], check=False).stdout.strip()
    v["k6"] = run(["docker", "run", "--rm", K6_IMAGE, "version"], check=False).stdout.strip()
    v["docker"] = run(["docker", "--version"], check=False).stdout.strip()
    info = run(["docker", "info", "--format", "{{.NCPU}}|{{.MemTotal}}|{{.OperatingSystem}}|{{.OSType}}/{{.Architecture}}|{{.ServerVersion}}"],
               check=False).stdout.strip().split("|")
    if len(info) == 5:
        v["host"] = (f"Docker sunucusu: {info[2]} ({info[3]}), Docker {info[4]}; "
                     f"Docker'ın görebildiği kaynak: {info[0]} CPU, {int(info[1]) / 2**30:.1f} GiB RAM")
    # Güç modu/pil durumu konteynerin içinden okunamaz; kullanıcı notu olarak kaydedilir.
    v["power"] = os.environ.get("BENCH_POWER_NOTE", "kaydedilmedi (konteynerden okunamaz; makinenin şebekeye bağlı ve yüksek performans modunda olması önerilir)")
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--stacks", default="go,spring")
    ap.add_argument("--vus", type=int, default=64)
    ap.add_argument("--phase-seconds", type=int, default=20)
    ap.add_argument("--warmup", type=int, default=180)
    ap.add_argument("--phases", default="", help="virgülle ayrılmış alt küme (varsayılan: hepsi)")
    ap.add_argument("--cold-round", action="store_true", help="normal turlara ek olarak ısınmasız bir tur (her yığın için) koş")
    ap.add_argument("--cold-phase-seconds", type=int, default=60, help="ısınmasız turda endpoint başına süre (varsayılan 60)")
    args = ap.parse_args()
    args.phases = [p for p in args.phases.split(",") if p]
    stacks = args.stacks.split(",")

    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "versions.json").write_text(json.dumps(collect_versions(), indent=2), encoding="utf-8")
    # Şablonu bir kez "görünür" işaretle (init.sql içindeki VACUUM bunu kuramıyor); kopyalar bunu miras alır.
    if STORE != "valkey":
        psql("bench_tpl", "VACUUM (FREEZE, ANALYZE)")

    for rnd in range(1, args.rounds + 1):
        order = stacks if rnd % 2 == 1 else list(reversed(stacks))  # sıra etkisini dengelemek için dönüşümlü
        for name in order:
            run_stack(name, rnd, args)
    if args.cold_round:
        cold_args = argparse.Namespace(**vars(args))
        cold_args.warmup = 0
        cold_args.phase_seconds = args.cold_phase_seconds
        order = stacks if (args.rounds + 1) % 2 == 1 else list(reversed(stacks))
        for name in order:
            run_stack(name, 1, cold_args, cold=True)
    print("\nbitti. ham sonuclar:", RAW)


if __name__ == "__main__":
    sys.exit(main())
