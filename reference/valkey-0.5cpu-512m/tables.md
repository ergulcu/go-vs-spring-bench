### Genel ölçümler

| Metrik | Go | Spring Boot |
|---|---:|---:|
| Soğuk başlangıç (konteyner → /health 200), sn | 0,80 | 15,16 |
| İlk istek gecikmesi (ms) | 3 | 178 |
| İkinci istek gecikmesi (ms) | 2,0 | 67,6 |
| Boşta bellek (MiB) | 2 | 139 |
| Isınma sonrası bellek (MiB) | 14 | 416 |
| Test boyunca en yüksek bellek (MiB) | 59 | 432 |
| İmaj boyutu (MB) | 5 | 146 |

### Throughput ve gecikme

| Endpoint | Go rps | Spring rps | Go/Spring | Go p50 | Spring p50 | Go p95 | Spring p95 | Go p99 | Spring p99 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GET /health | 6.341 | 4.301 | 1,47x | 2,3 | 1,7 | 76,5 | 91,2 | 83,7 | 94,3 |
| GET /items | 1.304 | 928 | 1,41x | 24,6 | 91,4 | 96,8 | 195,4 | 111,9 | 292,3 |
| GET /items/{id} | 3.798 | 1.447 | 2,63x | 4,1 | 4,8 | 80,6 | 101,4 | 86,9 | 197,7 |
| GET /items/search | 2.894 | 1.458 | 1,99x | 5,8 | 4,7 | 84,7 | 102,8 | 90,3 | 197,9 |
| GET /cpu | 221 | 190 | 1,16x | 289,2 | 300,3 | 504,9 | 600,4 | 703,9 | 800,9 |
| POST /orders | 3.281 | 1.694 | 1,94x | 5,0 | 4,1 | 81,8 | 100,8 | 87,1 | 194,4 |
| POST /items | 3.251 | 1.601 | 2,03x | 5,1 | 4,5 | 81,0 | 101,1 | 86,2 | 195,2 |
| PUT /items/{id} | 3.046 | 1.533 | 1,99x | 5,4 | 5,1 | 82,5 | 101,1 | 86,7 | 195,2 |
| DELETE /items/{id} | 3.924 | 1.287 | 3,05x | 4,1 | 5,1 | 79,6 | 101,5 | 84,3 | 199,1 |
| GET /stores/{id}/sales-report | 363 | 253 | 1,44x | 189,9 | 198,3 | 289,9 | 697,4 | 380,9 | 1.001,1 |
| GET /reports/sales | 9 | 5 | 1,62x | 7.026,3 | 11.607,8 | 8.976,8 | 18.332,7 | 9.412,8 | 20.039,9 |
| POST /base64 | 4.661 | 3.117 | 1,50x | 3,3 | 2,2 | 80,9 | 93,1 | 86,4 | 95,9 |
| GET /factorial?n=1000 | 2.661 | 583 | 4,57x | 6,1 | 100,1 | 88,6 | 200,8 | 95,0 | 389,0 |

_Gecikmeler ms cinsinden._

### Kaynak kullanımı (yük altında)

| Endpoint | Go CPU % | Spring CPU % | Go RAM MiB | Spring RAM MiB | Go RAM tepe | Spring RAM tepe | DB CPU % (Go turu) | DB CPU % (Spring turu) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GET /health | 48 | 48 | 15 | 420 | 17 | 421 | 2 | 2 |
| GET /items | 48 | 47 | 18 | 420 | 19 | 420 | 50 | 49 |
| GET /items/{id} | 48 | 48 | 16 | 420 | 18 | 421 | 41 | 35 |
| GET /items/search | 47 | 48 | 16 | 420 | 17 | 421 | 42 | 39 |
| GET /cpu | 47 | 47 | 16 | 420 | 17 | 421 | 2 | 2 |
| POST /orders | 48 | 48 | 16 | 420 | 17 | 421 | 62 | 34 |
| POST /items | 48 | 47 | 17 | 420 | 18 | 421 | 69 | 39 |
| PUT /items/{id} | 48 | 47 | 16 | 420 | 18 | 421 | 58 | 34 |
| DELETE /items/{id} | 48 | 47 | 16 | 422 | 18 | 422 | 63 | 23 |
| GET /stores/{id}/sales-report | 47 | 48 | 18 | 422 | 20 | 423 | 14 | 20 |
| GET /reports/sales | 7 | 15 | 44 | 424 | 59 | 432 | 382 | 330 |
| POST /base64 | 47 | 48 | 19 | 416 | 40 | 417 | 2 | 2 |
| GET /factorial?n=1000 | 47 | 47 | 17 | 416 | 19 | 421 | 2 | 2 |

### Veri bekleme süresi ve uygulama içi süre (sunucu tarafı, istek başına ortalama ms)

| Endpoint | Go veri ms | Go uygulama ms | Go veri % | Spring veri ms | Spring uygulama ms | Spring veri % |
|---|---:|---:|---:|---:|---:|---:|
| GET /health | 0,000 | 0,017 | 0 | 0,000 | 0,058 | 0 |
| GET /items | 39,284 | 0,021 | 100 | 56,851 | 0,076 | 100 |
| GET /items/{id} | 12,835 | 0,014 | 100 | 19,364 | 0,115 | 99 |
| GET /items/search | 16,844 | 0,020 | 100 | 26,998 | 0,173 | 99 |
| GET /cpu | 0,000 | 29,016 | 0 | 0,000 | 106,620 | 0 |
| POST /orders | 15,212 | 0,036 | 100 | 21,348 | 0,203 | 99 |
| POST /items | 15,185 | 0,055 | 100 | 22,491 | 0,130 | 99 |
| PUT /items/{id} | 15,664 | 0,037 | 100 | 20,632 | 0,245 | 99 |
| DELETE /items/{id} | 12,222 | 0,016 | 100 | 21,126 | 4,497 | 82 |
| GET /stores/{id}/sales-report | 151,855 | 2,984 | 98 | 179,396 | 8,342 | 96 |
| GET /reports/sales | 6.722,926 | 0,627 | 100 | 10.529,941 | 20,527 | 100 |
| POST /base64 | 0,000 | 0,096 | 0 | 0,000 | 0,165 | 0 |
| GET /factorial?n=1000 | 0,000 | 0,594 | 0 | 0,000 | 19,829 | 0 |

### Isınmasız tur (60 sn faz, ısınma yükü yok)

| Endpoint | Go rps | Spring rps | Go/Spring | Go ısınmasız/ısınmalı | Spring ısınmasız/ısınmalı | Go p99 | Spring p99 |
|---|---:|---:|---:|---:|---:|---:|---:|
| GET /health | 6.394 | 1.279 | 5,00x | 1,01x | 0,30x | 83,7 | 199,9 |
| GET /items | 1.460 | 412 | 3,54x | 1,12x | 0,44x | 99,8 | 698,7 |
| GET /items/{id} | 3.806 | 1.435 | 2,65x | 1,00x | 0,99x | 85,7 | 198,9 |
| GET /items/search | 2.859 | 1.452 | 1,97x | 0,99x | 1,00x | 89,6 | 199,1 |
| GET /cpu | 222 | 151 | 1,47x | 1,01x | 0,79x | 697,7 | 1.541,7 |
| POST /orders | 3.935 | 998 | 3,94x | 1,20x | 0,59x | 84,9 | 296,5 |
| POST /items | 3.763 | 1.478 | 2,55x | 1,16x | 0,92x | 85,4 | 198,9 |
| PUT /items/{id} | 3.445 | 1.560 | 2,21x | 1,13x | 1,02x | 86,3 | 192,5 |
| DELETE /items/{id} | 3.890 | 1.697 | 2,29x | 0,99x | 1,32x | 84,1 | 193,5 |
| GET /stores/{id}/sales-report | 418 | 197 | 2,12x | 1,15x | 0,78x | 293,0 | 2.900,0 |
| GET /reports/sales | 9 | 7 | 1,21x | 1,02x | 1,36x | 9.514,8 | 15.433,9 |
| POST /base64 | 4.769 | 2.497 | 1,91x | 1,02x | 0,80x | 86,5 | 99,9 |
| GET /factorial?n=1000 | 2.768 | 97 | 28,64x | 1,04x | 0,17x | 93,4 | 4.878,6 |

### CPU çalışma süresi (yük süresince harcanan toplam CPU)

| Endpoint | Go CPU sn | Spring CPU sn | Go ms/istek | Spring ms/istek | Spring/Go | Veri deposu CPU sn (Go turu) | Veri deposu CPU sn (Spring turu) |
|---|---:|---:|---:|---:|---:|---:|---:|
| GET /health | 10,1 | 10,0 | 0,079 | 0,116 | 1,47x | 0,4 | 0,4 |
| GET /items | 10,1 | 10,1 | 0,385 | 0,542 | 1,41x | 10,5 | 10,5 |
| GET /items/{id} | 10,1 | 10,0 | 0,132 | 0,345 | 2,62x | 8,5 | 7,3 |
| GET /items/search | 10,0 | 10,0 | 0,173 | 0,341 | 1,97x | 8,8 | 8,3 |
| GET /cpu | 10,2 | 10,2 | 2,275 | 2,638 | 1,16x | 0,4 | 0,3 |
| POST /orders | 10,0 | 9,9 | 0,152 | 0,292 | 1,92x | 12,9 | 7,2 |
| POST /items | 10,0 | 9,9 | 0,154 | 0,309 | 2,00x | 14,6 | 8,1 |
| PUT /items/{id} | 10,1 | 9,9 | 0,165 | 0,323 | 1,96x | 12,1 | 7,2 |
| DELETE /items/{id} | 10,0 | 10,2 | 0,128 | 0,396 | 3,11x | 13,2 | 5,0 |
| GET /stores/{id}/sales-report | 10,1 | 10,2 | 1,380 | 1,975 | 1,43x | 3,0 | 4,3 |
| GET /reports/sales | 1,8 | 3,5 | 8,018 | 26,426 | 3,30x | 100,1 | 98,7 |
| POST /base64 | 10,0 | 10,0 | 0,107 | 0,160 | 1,49x | 0,3 | 0,3 |
| GET /factorial?n=1000 | 10,0 | 9,9 | 0,188 | 0,852 | 4,52x | 0,3 | 0,4 |

### Verimlilik: CPU başına throughput

| Endpoint | Go rps / %CPU | Spring rps / %CPU |
|---|---:|---:|
| GET /health | 132,4 | 90,4 |
| GET /items | 27,2 | 19,5 |
| GET /items/{id} | 78,6 | 30,1 |
| GET /items/search | 61,3 | 30,5 |
| GET /cpu | 4,7 | 4,1 |
| POST /orders | 68,3 | 35,6 |
| POST /items | 67,8 | 33,8 |
| PUT /items/{id} | 63,4 | 32,4 |
| DELETE /items/{id} | 81,7 | 27,3 |
| GET /stores/{id}/sales-report | 7,7 | 5,3 |
| GET /reports/sales | 1,3 | 0,3 |
| POST /base64 | 98,4 | 65,5 |
| GET /factorial?n=1000 | 56,8 | 12,4 |

### Hata oranı ve tur farkı

| Endpoint | Go hata % | Spring hata % | Go rps (min–maks tur) | Spring rps (min–maks tur) |
|---|---:|---:|---:|---:|
| GET /health | 0,00 | 0,00 | 6.070–6.459 | 1.995–4.394 |
| GET /items | 0,00 | 0,00 | 1.051–1.536 | 637–940 |
| GET /items/{id} | 0,00 | 0,00 | 3.411–4.039 | 1.339–1.622 |
| GET /items/search | 0,00 | 0,00 | 2.765–2.912 | 908–1.521 |
| GET /cpu | 0,00 | 0,00 | 203–234 | 180–193 |
| POST /orders | 0,00 | 0,00 | 2.937–3.540 | 1.411–1.735 |
| POST /items | 0,00 | 0,00 | 2.730–3.718 | 1.600–1.606 |
| PUT /items/{id} | 0,00 | 0,00 | 2.653–3.692 | 1.464–1.599 |
| DELETE /items/{id} | 0,00 | 0,00 | 3.486–3.997 | 953–1.298 |
| GET /stores/{id}/sales-report | 0,00 | 0,00 | 348–380 | 205–256 |
| GET /reports/sales | 0,00 | 0,00 | 8–9 | 4–7 |
| POST /base64 | 0,00 | 0,00 | 4.382–4.849 | 1.865–3.373 |
| GET /factorial?n=1000 | 0,00 | 0,00 | 2.560–2.875 | 500–588 |