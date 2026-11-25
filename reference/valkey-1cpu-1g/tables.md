### Genel ölçümler

| Metrik | Go | Spring Boot |
|---|---:|---:|
| Soğuk başlangıç (konteyner → /health 200), sn | 0,62 | 6,90 |
| İlk istek gecikmesi (ms) | 2 | 81 |
| İkinci istek gecikmesi (ms) | 1,8 | 4,1 |
| Boşta bellek (MiB) | 2 | 138 |
| Isınma sonrası bellek (MiB) | 15 | 650 |
| Test boyunca en yüksek bellek (MiB) | 57 | 683 |
| İmaj boyutu (MB) | 5 | 146 |

### Throughput ve gecikme

| Endpoint | Go rps | Spring rps | Go/Spring | Go p50 | Spring p50 | Go p95 | Spring p95 | Go p99 | Spring p99 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GET /health | 13.766 | 9.471 | 1,45x | 2,0 | 1,3 | 19,7 | 75,3 | 54,8 | 80,6 |
| GET /items | 3.004 | 1.928 | 1,56x | 11,1 | 7,9 | 64,3 | 95,6 | 72,1 | 106,8 |
| GET /items/{id} | 8.022 | 4.158 | 1,93x | 3,8 | 2,6 | 42,4 | 84,7 | 57,7 | 91,0 |
| GET /items/search | 6.126 | 3.365 | 1,82x | 5,1 | 2,9 | 54,2 | 88,5 | 61,1 | 95,9 |
| GET /cpu | 471 | 362 | 1,30x | 118,7 | 195,5 | 211,8 | 300,3 | 300,1 | 399,4 |
| POST /orders | 7.617 | 3.857 | 1,97x | 4,1 | 2,6 | 48,8 | 86,0 | 57,5 | 92,5 |
| POST /items | 7.544 | 3.637 | 2,07x | 4,1 | 3,1 | 50,1 | 86,2 | 57,0 | 92,9 |
| PUT /items/{id} | 7.514 | 3.676 | 2,04x | 4,1 | 2,9 | 46,0 | 85,9 | 57,6 | 93,4 |
| DELETE /items/{id} | 7.960 | 2.887 | 2,76x | 3,8 | 3,0 | 41,7 | 89,2 | 55,3 | 99,0 |
| GET /stores/{id}/sales-report | 807 | 582 | 1,39x | 86,7 | 96,5 | 105,1 | 298,0 | 162,6 | 465,9 |
| GET /reports/sales | 9 | 9 | 1,00x | 6.571,3 | 6.699,0 | 8.375,6 | 9.910,1 | 9.323,4 | 13.026,9 |
| POST /base64 | 9.327 | 6.804 | 1,37x | 3,1 | 1,8 | 45,9 | 78,6 | 59,9 | 83,2 |
| GET /factorial?n=1000 | 5.534 | 1.309 | 4,23x | 5,5 | 11,8 | 57,9 | 99,1 | 65,6 | 104,1 |

_Gecikmeler ms cinsinden._

### Kaynak kullanımı (yük altında)

| Endpoint | Go CPU % | Spring CPU % | Go RAM MiB | Spring RAM MiB | Go RAM tepe | Spring RAM tepe | DB CPU % (Go turu) | DB CPU % (Spring turu) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GET /health | 96 | 95 | 15 | 653 | 16 | 654 | 2 | 2 |
| GET /items | 95 | 97 | 18 | 653 | 19 | 654 | 99 | 93 |
| GET /items/{id} | 95 | 96 | 16 | 654 | 17 | 655 | 82 | 64 |
| GET /items/search | 94 | 96 | 16 | 654 | 17 | 654 | 84 | 74 |
| GET /cpu | 94 | 94 | 16 | 654 | 17 | 655 | 1 | 1 |
| POST /orders | 94 | 96 | 16 | 654 | 17 | 655 | 120 | 67 |
| POST /items | 95 | 96 | 16 | 654 | 17 | 655 | 130 | 71 |
| PUT /items/{id} | 95 | 95 | 16 | 654 | 18 | 655 | 109 | 64 |
| DELETE /items/{id} | 93 | 96 | 17 | 657 | 18 | 658 | 133 | 56 |
| GET /stores/{id}/sales-report | 94 | 95 | 19 | 656 | 20 | 657 | 25 | 40 |
| GET /reports/sales | 7 | 9 | 43 | 677 | 57 | 682 | 382 | 380 |
| POST /base64 | 95 | 95 | 18 | 682 | 34 | 683 | 2 | 2 |
| GET /factorial?n=1000 | 95 | 94 | 17 | 683 | 17 | 683 | 1 | 2 |

### Veri bekleme süresi ve uygulama içi süre (sunucu tarafı, istek başına ortalama ms)

| Endpoint | Go veri ms | Go uygulama ms | Go veri % | Spring veri ms | Spring uygulama ms | Spring veri % |
|---|---:|---:|---:|---:|---:|---:|
| GET /health | 0,000 | 0,006 | 0 | 0,000 | 0,026 | 0 |
| GET /items | 16,904 | 0,011 | 100 | 27,964 | 0,041 | 100 |
| GET /items/{id} | 6,062 | 0,009 | 100 | 7,371 | 0,051 | 99 |
| GET /items/search | 7,936 | 0,010 | 100 | 11,715 | 0,075 | 99 |
| GET /cpu | 0,000 | 8,828 | 0 | 0,000 | 50,399 | 0 |
| POST /orders | 6,539 | 0,017 | 100 | 8,288 | 0,090 | 99 |
| POST /items | 6,452 | 0,021 | 100 | 9,439 | 0,083 | 99 |
| PUT /items/{id} | 6,559 | 0,019 | 100 | 8,554 | 0,114 | 99 |
| DELETE /items/{id} | 5,999 | 0,006 | 100 | 10,191 | 0,999 | 91 |
| GET /stores/{id}/sales-report | 68,147 | 1,407 | 98 | 81,159 | 3,100 | 96 |
| GET /reports/sales | 6.370,551 | 0,607 | 100 | 6.367,237 | 4,152 | 100 |
| POST /base64 | 0,000 | 0,047 | 0 | 0,000 | 0,069 | 0 |
| GET /factorial?n=1000 | 0,000 | 0,275 | 0 | 0,000 | 6,824 | 0 |

### Isınmasız tur (60 sn faz, ısınma yükü yok)

| Endpoint | Go rps | Spring rps | Go/Spring | Go ısınmasız/ısınmalı | Spring ısınmasız/ısınmalı | Go p99 | Spring p99 |
|---|---:|---:|---:|---:|---:|---:|---:|
| GET /health | 10.853 | 3.608 | 3,01x | 0,79x | 0,38x | 58,1 | 97,6 |
| GET /items | 2.143 | 1.177 | 1,82x | 0,71x | 0,61x | 97,5 | 206,3 |
| GET /items/{id} | 6.682 | 3.101 | 2,15x | 0,83x | 0,75x | 59,8 | 98,3 |
| GET /items/search | 5.220 | 2.556 | 2,04x | 0,85x | 0,76x | 62,6 | 103,6 |
| GET /cpu | 453 | 355 | 1,28x | 0,96x | 0,98x | 307,1 | 500,8 |
| POST /orders | 7.395 | 2.914 | 2,54x | 0,97x | 0,76x | 57,1 | 98,4 |
| POST /items | 6.891 | 2.835 | 2,43x | 0,91x | 0,78x | 57,3 | 99,8 |
| PUT /items/{id} | 6.447 | 3.105 | 2,08x | 0,86x | 0,84x | 58,7 | 95,3 |
| DELETE /items/{id} | 6.332 | 3.894 | 1,63x | 0,80x | 1,35x | 57,8 | 91,6 |
| GET /stores/{id}/sales-report | 766 | 504 | 1,52x | 0,95x | 0,87x | 168,4 | 610,6 |
| GET /reports/sales | 9 | 9 | 1,00x | 0,96x | 0,96x | 10.140,9 | 12.749,4 |
| POST /base64 | 9.166 | 6.640 | 1,38x | 0,98x | 0,98x | 59,5 | 83,4 |
| GET /factorial?n=1000 | 5.186 | 1.096 | 4,73x | 0,94x | 0,84x | 67,0 | 194,7 |

### CPU çalışma süresi (yük süresince harcanan toplam CPU)

| Endpoint | Go CPU sn | Spring CPU sn | Go ms/istek | Spring ms/istek | Spring/Go | Veri deposu CPU sn (Go turu) | Veri deposu CPU sn (Spring turu) |
|---|---:|---:|---:|---:|---:|---:|---:|
| GET /health | 20,1 | 20,0 | 0,073 | 0,105 | 1,44x | 0,4 | 0,3 |
| GET /items | 20,0 | 20,1 | 0,333 | 0,520 | 1,56x | 21,0 | 19,3 |
| GET /items/{id} | 19,9 | 20,0 | 0,124 | 0,240 | 1,94x | 17,6 | 13,3 |
| GET /items/search | 20,0 | 20,0 | 0,163 | 0,296 | 1,81x | 18,0 | 15,3 |
| GET /cpu | 20,2 | 20,3 | 2,132 | 2,766 | 1,30x | 0,3 | 0,3 |
| POST /orders | 20,0 | 20,0 | 0,132 | 0,258 | 1,96x | 25,5 | 13,8 |
| POST /items | 20,1 | 19,9 | 0,133 | 0,274 | 2,06x | 27,7 | 14,7 |
| PUT /items/{id} | 19,9 | 20,0 | 0,133 | 0,270 | 2,04x | 22,9 | 13,5 |
| DELETE /items/{id} | 19,6 | 20,1 | 0,122 | 0,346 | 2,84x | 27,7 | 12,2 |
| GET /stores/{id}/sales-report | 20,1 | 20,2 | 1,242 | 1,718 | 1,38x | 5,3 | 8,6 |
| GET /reports/sales | 1,8 | 2,4 | 7,705 | 9,807 | 1,27x | 99,8 | 101,7 |
| POST /base64 | 20,0 | 20,0 | 0,107 | 0,146 | 1,36x | 0,4 | 0,4 |
| GET /factorial?n=1000 | 20,1 | 20,1 | 0,181 | 0,763 | 4,21x | 0,3 | 0,4 |

### Verimlilik: CPU başına throughput

| Endpoint | Go rps / %CPU | Spring rps / %CPU |
|---|---:|---:|
| GET /health | 142,7 | 99,5 |
| GET /items | 31,7 | 19,8 |
| GET /items/{id} | 84,6 | 43,3 |
| GET /items/search | 65,2 | 35,0 |
| GET /cpu | 5,0 | 3,9 |
| POST /orders | 81,0 | 40,2 |
| POST /items | 79,2 | 37,9 |
| PUT /items/{id} | 79,5 | 38,6 |
| DELETE /items/{id} | 85,6 | 30,0 |
| GET /stores/{id}/sales-report | 8,6 | 6,1 |
| GET /reports/sales | 1,3 | 1,0 |
| POST /base64 | 97,9 | 71,4 |
| GET /factorial?n=1000 | 58,4 | 13,9 |

### Hata oranı ve tur farkı

| Endpoint | Go hata % | Spring hata % | Go rps (min–maks tur) | Spring rps (min–maks tur) |
|---|---:|---:|---:|---:|
| GET /health | 0,00 | 0,00 | 12.230–14.409 | 8.713–9.760 |
| GET /items | 0,00 | 0,00 | 2.767–3.138 | 1.870–1.936 |
| GET /items/{id} | 0,00 | 0,00 | 7.105–8.227 | 3.991–4.160 |
| GET /items/search | 0,00 | 0,00 | 5.740–6.176 | 2.938–3.374 |
| GET /cpu | 0,00 | 0,00 | 444–476 | 353–378 |
| POST /orders | 0,00 | 0,00 | 6.714–7.768 | 3.563–3.923 |
| POST /items | 0,00 | 0,00 | 7.095–7.643 | 3.367–3.744 |
| PUT /items/{id} | 0,00 | 0,00 | 6.267–7.555 | 3.431–3.759 |
| DELETE /items/{id} | 0,00 | 0,00 | 7.476–8.050 | 2.713–3.482 |
| GET /stores/{id}/sales-report | 0,00 | 0,00 | 751–813 | 542–584 |
| GET /reports/sales | 0,00 | 0,00 | 8–9 | 7–9 |
| POST /base64 | 0,00 | 0,00 | 8.849–9.393 | 5.914–7.047 |
| GET /factorial?n=1000 | 0,00 | 0,00 | 5.368–5.568 | 1.271–1.360 |