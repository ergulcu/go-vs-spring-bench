# Go vs Spring Boot: performans karşılaştırması

Aynı 14 endpoint'li REST API'nin **Go** (net/http + pgx) ve **Spring Boot** (Spring MVC + JdbcClient) ile yazılmış iki sürümü, aynı veri deposu (**PostgreSQL 18** ya da bellek içi **Valkey 8**) üzerinde, aynı Docker kaynak limitleriyle yük altında karşılaştırılır: throughput, gecikme (p50/p95/p99), CPU, RAM, soğuk başlangıç, imaj boyutu ve build süresi.

Sonuçların yorumu: **[Java vs Go: veritabanı hızlanınca fark açılıyor mu?](https://ergulcu.com/posts/java-vs-go)** ([English](https://ergulcu.com/en/posts/java-vs-go)). Yazıdaki koşunun tüm raporları ve ham verisi [`reference/`](reference/) klasöründe.

Tek komutla çalışır; makinenizde Go, Java, Maven, Python veya k6 kurulu olması gerekmez. Yalnızca **Docker** (Compose v2) yeterlidir.

> **English:** a self-contained benchmark of the same 14-endpoint REST API written in Go and Spring Boot, against PostgreSQL and in-memory Valkey, under identical container limits (1 CPU / 1 GiB and 0.5 CPU / 512 MiB). Everything runs in Docker: `docker compose run --rm runner`. The generated report is in Turkish; numbers and charts are language-neutral. The write-up is [Java vs Go: does the gap widen when the database gets faster?](https://ergulcu.com/en/posts/java-vs-go); the author's run behind it is in [reference/](reference/) (start with [reference/index.html](reference/index.html)).

## Hızlı başlangıç

```bash
git clone https://github.com/ergulcu/go-vs-spring-bench.git && cd go-vs-spring-bench

docker compose run --rm runner --quick     # kısa deneme (birkaç on dakika): 1 tur, 4 senaryo
docker compose run --rm runner             # yazıdaki tam koşu: 3 tur + ısınmasız tur, 4 senaryo, build süreleri (~6 saat)
```

Bittiğinde raporlar `results/` altında:

| Dosya | İçerik |
|---|---|
| `results/index.html` | Senaryoları yan yana özetler |
| `results/1cpu-1g/report.html` | PostgreSQL, uygulama başına 1 CPU / 1 GiB |
| `results/0.5cpu-512m/report.html` | PostgreSQL, uygulama başına 0,5 CPU / 512 MiB |
| `results/valkey-1cpu-1g/report.html` | Valkey, uygulama başına 1 CPU / 1 GiB |
| `results/valkey-0.5cpu-512m/report.html` | Valkey, uygulama başına 0,5 CPU / 512 MiB |
| `results/<senaryo>/raw/` | Ham k6 çıktıları ve tur sonuçları (JSON) |

Yazarın kendi makinesindeki ölçüm (yazıdaki sayılar) [`reference/index.html`](reference/index.html) dosyasında, doğrudan açılabilir: 4 senaryo, 14 endpoint (Valkey'de 13), 3 turun ortancası ve ısınmasız tur. Makine: 16 CPU / 7,4 GiB RAM görünen Docker Desktop (Windows), şebekede, en iyi performans modunda.

## Seçenekler

```bash
docker compose run --rm runner --limits 1:1g              # yalnızca tek limit (cpu:bellek)
docker compose run --rm runner --limits 2:2g,0.5:512m     # istediğiniz limitler (varsayılan: 1:1g,0.5:512m)
docker compose run --rm runner --rounds 5 --warmup 240    # daha çok tur, daha uzun ısınma
docker compose run --rm runner --no-build-times           # build süresi ölçümünü atla (temiz build ~10 dk)
docker compose run --rm runner --limits 2:2g --extras    # ek doğrulamalar (yalnızca 2 CPU senaryosunda): CPU kotası (CFS throttling) ve indeks kullanımı (pg_stat)
docker compose run --rm runner --stores postgres          # yalnızca PostgreSQL (varsayılan: postgres,valkey)
docker compose run --rm runner --stores valkey            # yalnızca bellek içi Valkey (13 endpoint, /stats yok)
docker compose run --rm runner --no-cold-round            # ısınmasız turu atla
docker compose run --rm runner --help
```

**Valkey senaryosu:** veritabanı darboğaz olduğunda (ör. `/stats`) iki dil arasındaki fark kaybolur. `--stores valkey` aynı endpoint'leri, aynı JSON çıktısıyla, PostgreSQL yerine Valkey (Redis'in açık kaynak çatalı, bellek içi) üzerinden sunar; veri erişimi neredeyse bedava olduğu için uygulamanın kendi hızı öne çıkar. Aynı deterministik veri yüklenir, yazmalar Lua betikleriyle tek turda yapılır. Her iki uygulamanın her iki depodaki çıktıları örnek isteklerde birebir aynıdır. `/stats` bu modda yoktur (SQL `GROUP BY`'ın bellek içi karşılığı yok).

Varsayılan: 3 tur, 180 sn ısınma, endpoint başına 20 sn, 64 eşzamanlı sanal kullanıcı; ayrıca her senaryoda ısınmasız bir tur (taze konteyner, endpoint başına 60 sn). Aynı anda yalnızca bir uygulama çalışır; tur sırası dönüşümlüdür (Go→Spring, Spring→Go, Go→Spring), sonuç turların ortancasıdır.

## Gereksinimler

- Docker Desktop (Windows / macOS) veya Docker Engine + Compose v2 (Linux). Runner, Docker'ı `/var/run/docker.sock` üzerinden kullanır.
- Docker'a en az **8 GiB RAM** ve **8+ CPU** verilmesi önerilir (veri deposu 8 CPU / 4 GiB, uygulama 1 CPU / 1 GiB ister). CPU sayısı 8'den azsa veritabanı limiti otomatik düşürülür ve konteynerler birbirini etkiler; sonuçlar referanstan sapar.
- İlk koşuda imajlar (PostgreSQL, Go, Temurin JDK, Maven, k6) indirilir; Maven ve Go bağımlılıkları için internet gerekir.
- Ölçüm sırasında makineyi başka işlerle yormayın; dizüstüyse şebekeye bağlayıp yüksek performans moduna alın (konteynerden okunamaz). Raporda notlamak için: `BENCH_POWER_NOTE="şebeke, en iyi performans" docker compose run --rm runner`.

## Neyi ölçer, nasıl?

14 endpoint: `GET /health`, `GET /items` (sayfalı liste), `GET /items/{id}`, `POST /items`, `PUT /items/{id}`, `DELETE /items/{id}`, `GET /items/search`, `GET /stats` (ağır toplama), `POST /orders` (transaction), `GET /cpu` (veritabanısız CPU işi), `GET /stores/{id}/sales-report` (**uygulama mantığı**: mağazanın ham satış satırları çekilip günlük ve aylık toplamlar, en iyi gün ve aylık büyüme SQL ile değil kodda hesaplanır) ve `GET /reports/sales` (20 mağazanın 40.000 satışını mağaza mağaza raporlar; toplamlar **veri deposunda** hesaplanır: PostgreSQL'de SQL `GROUP BY`, Valkey'de Lua betiği), `POST /base64` (isteğin ~2 KB'lık gövdesini Base64'e çevirir) ve `GET /factorial?n=1000` (büyük tamsayıyla 1000! hesaplar). Son ikisi veritabanı kullanmaz, saf uygulama mantığıdır. Raporda throughput ve gecikmenin yanı sıra CPU yüzdesi, harcanan CPU süresi (sn), istek başına CPU süresi (ms) ve **veri bekleme süresi** (uygulamanın içinde ölçülüp `Server-Timing` başlığıyla iletilen: veri deposuna gönderilmesinden sonuçların okunup çözülmesine kadar geçen süre, ve uygulama içi süre) de bulunur.

Her tur için: veritabanı şablondan yeniden oluşturulur → API konteyneri sıfırdan başlar (soğuk başlangıç ölçülür) → karışık yükle ısınma (JIT için) → ısınmanın eklediği satırlar silinip tablo her iki yığın için de aynı duruma getirilir → 14 endpoint sırayla k6 ile yüklenir (kapalı döngü), `docker stats` ile CPU/RAM örneklenir; ayrıca her faz için konteynerin cgroup sayacından (`cpu.stat`) **harcadığı toplam CPU süresi (sn) ve istek başına CPU süresi (ms)** okunur. Ayrıntı ve sınırlılıklar raporun "Metodoloji" ve "Sınırlılıklar" bölümlerinde.

## Klasörler

| Klasör | |
|---|---|
| `go-api/`, `spring-api/` | İki uygulama ve Dockerfile'ları |
| `db/` | PostgreSQL imajı, şema ve 100.000 satırlık tohum veri (`init.sql`) |
| `k6/test.js` | Yük senaryosu |
| `runner/` | Orkestratör konteyneri (Python + Docker CLI) |
| `scripts/` | `run_all.py` (giriş noktası), `bench.py` (ölçüm), `build_time.py`, `report*.py` ve ek doğrulama betikleri |
| `reference/` | Yazıdaki ölçüm: 4 senaryonun raporları, grafikleri ve ham verisi |
| `results/` | Sizin koşularınızın çıktısı (git'e girmez; önceki koşu `results/_previous/` altına taşınır) |

## Notlar

- `compose.yaml` içindeki PostgreSQL ayarları (`fsync=off`, `full_page_writes=off`, `synchronous_commit=off`) **yalnızca benchmark içindir**; amaç diski değil uygulamaları ölçmektir. Üretimde kullanmayın.
- Kod bilerek en sade haliyle yazıldı. JVM/GC ayarı, sanal iş parçacıkları, GraalVM native image, `GOGC`/`GOMEMLIMIT` denenmedi; sonuçları değiştirebilirler. Pull request'ler memnuniyetle karşılanır.
- Koşu bittiğinde `bench-*` konteynerleri silinir. Runner'ın oluşturduğu ağı da kaldırmak için: `docker compose down`.
- Linux'ta runner root olarak çalıştığından `results/` dosyaları root sahipli olur.
- Lisans: MIT ([LICENSE](LICENSE)).
- Küçük limitte (0,5 CPU) ağır endpoint'ler (`/stats`, `/reports/sales`) saniyede birkaç istek işler; 20 sn'lik fazda az istek tamamlandığı için o satırlardaki p95/p99 gürültülüdür. Daha güvenilir sayı için `--phase-seconds 60` kullanın.
