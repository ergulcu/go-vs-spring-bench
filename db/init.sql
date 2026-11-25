-- Şablon veritabanı: her test turundan önce "bench" bu şablondan yeniden oluşturulur,
-- böylece Go ve Spring Boot birebir aynı başlangıç verisiyle test edilir.
CREATE DATABASE bench_tpl;
\c bench_tpl

CREATE TABLE items (
    id          bigserial PRIMARY KEY,
    name        text        NOT NULL,
    category    text        NOT NULL,
    price_cents integer     NOT NULL,
    stock       integer     NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
) WITH (fillfactor = 80);  -- sayfalarda boşluk bırakır: price/stock güncellemeleri HOT olabilir (indeks yazmadan)

CREATE TABLE orders (
    id          bigserial PRIMARY KEY,
    item_id     bigint      NOT NULL,
    quantity    integer     NOT NULL,
    total_cents bigint      NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Satış raporu uç noktaları (GET /stores/{id}/sales-report, GET /reports/sales) için mağaza ve satış verisi.
-- Günlük/aylık toplamlar SQL ile değil uygulama kodunda hesaplanır; bu yüzden tabloda yalnızca ham satış satırları var.
CREATE TABLE stores (
    id   integer PRIMARY KEY,
    name text NOT NULL,
    city text NOT NULL
);

CREATE TABLE sales (
    id           bigint    PRIMARY KEY,
    store_id     integer   NOT NULL,
    sold_at      timestamp NOT NULL,
    quantity     integer   NOT NULL,
    amount_cents bigint    NOT NULL
);

INSERT INTO stores (id, name, city)
SELECT g, 'Store ' || lpad(g::text, 2, '0'), (ARRAY['Istanbul', 'Ankara', 'Izmir', 'Bursa', 'Antalya'])[1 + g % 5]
FROM generate_series(1, 20) AS g;

-- 20 mağaza x 2.000 satış = 40.000 satır, 2024-01-01 .. 2025-12-31 (731 gün). Deterministik (random yok): iki yığın aynı veriyi görür.
INSERT INTO sales (id, store_id, sold_at, quantity, amount_cents)
SELECT g, 1 + (g % 20),
       timestamp '2024-01-01' + (((g::bigint * 7919) % 731) * interval '1 day') + (((g::bigint * 104729) % 86400) * interval '1 second'),
       1 + (g % 5),
       500 + (g::bigint * 37) % 20000
FROM generate_series(1, 40000) AS g;

CREATE INDEX sales_store_idx ON sales (store_id);  -- tek mağaza raporu: WHERE store_id = ?

-- 100.000 ürün; isimler md5 olduğu için 4 karakterlik rastgele önek aramaları ~1-2 satır döner.
INSERT INTO items (id, name, category, price_cents, stock)
SELECT g, md5(g::text), 'cat-' || (g % 20), 100 + (g * 37) % 100000, 1000000
FROM generate_series(1, 100000) AS g;

SELECT setval(pg_get_serial_sequence('items', 'id'), 100000);

-- İndeksler (yalnızca sorguların gerçekten kullandıkları; her fazladan indeks yazmayı yavaşlatır):
--   items_pkey            -> GET /items, GET/PUT/DELETE /items/{id}, POST /orders (birincil anahtar)
--   items_name_lower_idx  -> GET /items/search (lower(name) LIKE 'xxxx%' önek araması)
-- Bilerek OLMAYANLAR:
--   category indeksi: GET /stats tüm tabloyu topluyor, hiçbir sorgu kullanmıyor. Kapsayan indeks (category) INCLUDE (price_cents, stock)
--     tek sorguyu 42 ms -> 20 ms'ye indirdi ama 64 eşzamanlı yük altında throughput kazandırmadı (~204 rps iki durumda da),
--     buna karşılık price/stock güncellemelerini HOT olmaktan çıkardı (HOT %0 -> %100 ile fillfactor=80 sade tasarımda). Bkz. results/index_ab.json
--   orders tablosu: yalnızca yazılıyor, okuma sorgusu yok.
CREATE INDEX items_name_lower_idx ON items (lower(name) text_pattern_ops);

-- VACUUM: görünürlük haritasını ve ipucu bitlerini önceden kurar, ilk okumalar ek yazma yapmaz.
-- FREEZE: tüm sayfaları "görünür" işaretler; kapsayan indeksin index-only scan yapabilmesi için gerekir.
-- Not: init sırasında bu VACUUM sayfaları tam işaretleyemiyor; scripts/bench.py başlangıçta aynısını yeniden çalıştırır.
VACUUM (FREEZE, ANALYZE);
