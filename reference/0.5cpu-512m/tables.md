### Genel ölçümler

| Metrik | Go | Spring Boot |
|---|---:|---:|
| Soğuk başlangıç (konteyner → /health 200), sn | 0,64 | 12,63 |
| İlk istek gecikmesi (ms) | 5 | 1.010 |
| İkinci istek gecikmesi (ms) | 2,4 | 86,0 |
| Boşta bellek (MiB) | 4 | 149 |
| Isınma sonrası bellek (MiB) | 20 | 406 |
| Test boyunca en yüksek bellek (MiB) | 105 | 438 |
| İmaj boyutu (MB) | 5 | 146 |

### Throughput ve gecikme

| Endpoint | Go rps | Spring rps | Go/Spring | Go p50 | Spring p50 | Go p95 | Spring p95 | Go p99 | Spring p99 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GET /health | 7.313 | 1.886 | 3,88x | 1,9 | 2,8 | 74,4 | 97,7 | 82,7 | 100,4 |
| GET /items | 2.065 | 1.031 | 2,00x | 8,4 | 95,2 | 87,4 | 101,6 | 91,9 | 196,1 |
| GET /items/{id} | 3.275 | 1.446 | 2,26x | 5,0 | 5,3 | 82,3 | 98,9 | 86,9 | 104,3 |
| GET /items/search | 3.056 | 1.760 | 1,74x | 5,4 | 3,9 | 82,6 | 96,3 | 87,3 | 99,4 |
| GET /stats | 240 | 240 | 1,00x | 269,4 | 268,4 | 325,9 | 424,0 | 382,3 | 527,6 |
| GET /cpu | 244 | 179 | 1,36x | 223,1 | 302,6 | 495,0 | 599,7 | 596,4 | 700,6 |
| POST /orders | 1.398 | 816 | 1,71x | 26,7 | 97,1 | 92,4 | 195,8 | 96,1 | 201,4 |
| POST /items | 3.095 | 1.665 | 1,86x | 5,3 | 4,0 | 83,1 | 97,9 | 87,2 | 101,1 |
| PUT /items/{id} | 3.094 | 1.776 | 1,74x | 5,3 | 4,0 | 82,9 | 96,9 | 87,3 | 100,7 |
| DELETE /items/{id} | 3.379 | 1.226 | 2,76x | 4,7 | 5,7 | 81,6 | 99,5 | 86,4 | 193,7 |
| GET /stores/{id}/sales-report | 317 | 223 | 1,42x | 198,7 | 292,2 | 294,6 | 597,7 | 381,8 | 803,4 |
| GET /reports/sales | 31 | 27 | 1,15x | 1.994,0 | 1.823,3 | 2.512,3 | 5.598,0 | 2.769,5 | 7.159,7 |
| POST /base64 | 4.554 | 3.484 | 1,31x | 3,3 | 1,8 | 81,6 | 92,8 | 87,5 | 95,9 |
| GET /factorial?n=1000 | 2.578 | 558 | 4,62x | 6,4 | 100,1 | 88,7 | 201,3 | 94,0 | 303,4 |

_Gecikmeler ms cinsinden._

### Kaynak kullanımı (yük altında)

| Endpoint | Go CPU % | Spring CPU % | Go RAM MiB | Spring RAM MiB | Go RAM tepe | Spring RAM tepe | DB CPU % (Go turu) | DB CPU % (Spring turu) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GET /health | 47 | 48 | 17 | 411 | 20 | 412 | 3 | 3 |
| GET /items | 47 | 48 | 18 | 412 | 19 | 413 | 41 | 25 |
| GET /items/{id} | 47 | 47 | 16 | 412 | 17 | 414 | 35 | 18 |
| GET /items/search | 47 | 48 | 17 | 413 | 18 | 414 | 81 | 47 |
| GET /stats | 13 | 17 | 18 | 412 | 19 | 414 | 765 | 769 |
| GET /cpu | 47 | 48 | 17 | 413 | 17 | 415 | 3 | 3 |
| POST /orders | 47 | 48 | 17 | 418 | 17 | 422 | 50 | 34 |
| POST /items | 47 | 48 | 16 | 421 | 17 | 422 | 48 | 33 |
| PUT /items/{id} | 47 | 48 | 16 | 421 | 18 | 422 | 47 | 32 |
| DELETE /items/{id} | 47 | 47 | 17 | 424 | 18 | 426 | 42 | 17 |
| GET /stores/{id}/sales-report | 47 | 48 | 29 | 426 | 34 | 427 | 39 | 36 |
| GET /reports/sales | 48 | 49 | 85 | 432 | 105 | 438 | 801 | 624 |
| POST /base64 | 48 | 47 | 28 | 430 | 68 | 430 | 3 | 3 |
| GET /factorial?n=1000 | 47 | 47 | 26 | 430 | 28 | 431 | 3 | 3 |

### Veri bekleme süresi ve uygulama içi süre (sunucu tarafı, istek başına ortalama ms)

| Endpoint | Go veri ms | Go uygulama ms | Go veri % | Spring veri ms | Spring uygulama ms | Spring veri % |
|---|---:|---:|---:|---:|---:|---:|
| GET /health | 0,000 | 0,017 | 0 | 0,000 | 0,222 | 0 |
| GET /items | 24,319 | 0,042 | 100 | 15,562 | 0,414 | 97 |
| GET /items/{id} | 14,672 | 0,020 | 100 | 8,961 | 0,248 | 97 |
| GET /items/search | 16,214 | 0,019 | 100 | 8,434 | 0,125 | 99 |
| GET /stats | 263,906 | 0,010 | 100 | 263,921 | 0,058 | 100 |
| GET /cpu | 0,000 | 24,931 | 0 | 0,000 | 109,948 | 0 |
| POST /orders | 41,967 | 0,044 | 100 | 38,818 | 0,536 | 99 |
| POST /items | 15,722 | 0,057 | 100 | 14,115 | 0,173 | 99 |
| PUT /items/{id} | 15,538 | 0,048 | 100 | 8,977 | 0,165 | 98 |
| DELETE /items/{id} | 13,787 | 0,013 | 100 | 12,365 | 2,000 | 86 |
| GET /stores/{id}/sales-report | 176,159 | 2,839 | 98 | 172,462 | 11,462 | 94 |
| GET /reports/sales | 2.019,747 | 0,347 | 100 | 2.191,494 | 6,878 | 100 |
| POST /base64 | 0,000 | 0,235 | 0 | 0,000 | 0,142 | 0 |
| GET /factorial?n=1000 | 0,000 | 0,807 | 0 | 0,000 | 17,082 | 0 |

### Isınmasız tur (60 sn faz, ısınma yükü yok)

| Endpoint | Go rps | Spring rps | Go/Spring | Go ısınmasız/ısınmalı | Spring ısınmasız/ısınmalı | Go p99 | Spring p99 |
|---|---:|---:|---:|---:|---:|---:|---:|
| GET /health | 7.514 | 1.381 | 5,44x | 1,03x | 0,73x | 82,2 | 199,2 |
| GET /items | 2.132 | 727 | 2,93x | 1,03x | 0,71x | 89,9 | 300,3 |
| GET /items/{id} | 3.257 | 1.255 | 2,59x | 0,99x | 0,87x | 86,6 | 195,2 |
| GET /items/search | 3.044 | 1.635 | 1,86x | 1,00x | 0,93x | 87,3 | 102,6 |
| GET /stats | 241 | 240 | 1,00x | 1,00x | 1,00x | 385,3 | 551,1 |
| GET /cpu | 239 | 192 | 1,24x | 0,98x | 1,07x | 602,6 | 997,7 |
| POST /orders | 1.368 | 729 | 1,88x | 0,98x | 0,89x | 95,8 | 294,7 |
| POST /items | 3.028 | 1.577 | 1,92x | 0,98x | 0,95x | 87,1 | 102,3 |
| PUT /items/{id} | 3.001 | 1.678 | 1,79x | 0,97x | 0,95x | 87,5 | 101,4 |
| DELETE /items/{id} | 3.323 | 2.049 | 1,62x | 0,98x | 1,67x | 86,5 | 99,7 |
| GET /stores/{id}/sales-report | 305 | 157 | 1,94x | 0,96x | 0,70x | 309,9 | 1.302,9 |
| GET /reports/sales | 31 | 31 | 0,99x | 1,00x | 1,16x | 2.611,0 | 6.294,3 |
| POST /base64 | 4.469 | 3.432 | 1,30x | 0,98x | 0,98x | 87,3 | 95,3 |
| GET /factorial?n=1000 | 2.460 | 481 | 5,11x | 0,95x | 0,86x | 94,8 | 400,2 |

### CPU çalışma süresi (yük süresince harcanan toplam CPU)

| Endpoint | Go CPU sn | Spring CPU sn | Go ms/istek | Spring ms/istek | Spring/Go | Veri deposu CPU sn (Go turu) | Veri deposu CPU sn (Spring turu) |
|---|---:|---:|---:|---:|---:|---:|---:|
| GET /health | 10,0 | 10,4 | 0,069 | 0,274 | 4,00x | 0,7 | 0,6 |
| GET /items | 10,1 | 10,3 | 0,243 | 0,501 | 2,07x | 8,7 | 5,2 |
| GET /items/{id} | 10,1 | 10,3 | 0,153 | 0,354 | 2,32x | 7,4 | 3,8 |
| GET /items/search | 10,1 | 10,0 | 0,164 | 0,282 | 1,72x | 17,2 | 10,1 |
| GET /stats | 2,7 | 3,5 | 0,562 | 0,723 | 1,29x | 162,1 | 162,2 |
| GET /cpu | 10,2 | 10,2 | 2,060 | 2,805 | 1,36x | 0,6 | 0,5 |
| POST /orders | 10,1 | 10,4 | 0,360 | 0,633 | 1,76x | 10,8 | 7,1 |
| POST /items | 10,1 | 10,0 | 0,162 | 0,300 | 1,85x | 10,2 | 7,0 |
| PUT /items/{id} | 10,1 | 10,0 | 0,162 | 0,280 | 1,73x | 10,1 | 6,7 |
| DELETE /items/{id} | 10,1 | 10,2 | 0,149 | 0,418 | 2,81x | 8,9 | 3,7 |
| GET /stores/{id}/sales-report | 10,1 | 10,3 | 1,581 | 2,268 | 1,43x | 8,5 | 7,5 |
| GET /reports/sales | 10,3 | 10,7 | 15,436 | 18,699 | 1,21x | 170,9 | 138,5 |
| POST /base64 | 10,1 | 10,0 | 0,110 | 0,143 | 1,30x | 0,7 | 0,6 |
| GET /factorial?n=1000 | 10,0 | 10,4 | 0,194 | 0,918 | 4,74x | 0,6 | 0,6 |

### Verimlilik: CPU başına throughput

| Endpoint | Go rps / %CPU | Spring rps / %CPU |
|---|---:|---:|
| GET /health | 154,0 | 39,6 |
| GET /items | 43,6 | 21,7 |
| GET /items/{id} | 69,3 | 30,5 |
| GET /items/search | 64,8 | 36,7 |
| GET /stats | 18,5 | 14,3 |
| GET /cpu | 5,2 | 3,7 |
| POST /orders | 29,8 | 16,9 |
| POST /items | 65,2 | 34,6 |
| PUT /items/{id} | 65,3 | 37,1 |
| DELETE /items/{id} | 71,2 | 25,9 |
| GET /stores/{id}/sales-report | 6,7 | 4,6 |
| GET /reports/sales | 0,6 | 0,5 |
| POST /base64 | 95,7 | 73,6 |
| GET /factorial?n=1000 | 54,5 | 11,8 |

### Hata oranı ve tur farkı

| Endpoint | Go hata % | Spring hata % | Go rps (min–maks tur) | Spring rps (min–maks tur) |
|---|---:|---:|---:|---:|
| GET /health | 0,00 | 0,00 | 7.289–7.359 | 1.555–2.665 |
| GET /items | 0,00 | 0,00 | 1.999–2.085 | 922–1.266 |
| GET /items/{id} | 0,00 | 0,00 | 3.220–3.350 | 1.354–2.056 |
| GET /items/search | 0,00 | 0,00 | 2.995–3.103 | 1.657–2.041 |
| GET /stats | 0,00 | 0,00 | 239–241 | 221–240 |
| GET /cpu | 0,00 | 0,00 | 236–244 | 176–182 |
| POST /orders | 0,00 | 0,00 | 1.309–1.416 | 741–830 |
| POST /items | 0,00 | 0,00 | 2.900–3.102 | 1.629–1.674 |
| PUT /items/{id} | 0,00 | 0,00 | 2.832–3.102 | 1.679–1.854 |
| DELETE /items/{id} | 0,00 | 0,00 | 3.007–3.447 | 1.203–1.394 |
| GET /stores/{id}/sales-report | 0,00 | 0,00 | 288–324 | 205–248 |
| GET /reports/sales | 0,00 | 0,00 | 31–31 | 25–30 |
| POST /base64 | 0,00 | 0,00 | 4.436–4.661 | 3.110–3.485 |
| GET /factorial?n=1000 | 0,00 | 0,00 | 2.423–2.601 | 535–581 |