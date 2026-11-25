### Genel ölçümler

| Metrik | Go | Spring Boot |
|---|---:|---:|
| Soğuk başlangıç (konteyner → /health 200), sn | 0,67 | 6,60 |
| İlk istek gecikmesi (ms) | 5 | 522 |
| İkinci istek gecikmesi (ms) | 1,6 | 4,5 |
| Boşta bellek (MiB) | 4 | 155 |
| Isınma sonrası bellek (MiB) | 20 | 669 |
| Test boyunca en yüksek bellek (MiB) | 100 | 686 |
| İmaj boyutu (MB) | 5 | 146 |

### Throughput ve gecikme

| Endpoint | Go rps | Spring rps | Go/Spring | Go p50 | Spring p50 | Go p95 | Spring p95 | Go p99 | Spring p99 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GET /health | 13.664 | 9.258 | 1,48x | 2,0 | 1,3 | 20,6 | 74,9 | 55,5 | 81,2 |
| GET /items | 3.931 | 3.552 | 1,11x | 8,2 | 3,1 | 60,2 | 86,4 | 65,2 | 89,8 |
| GET /items/{id} | 6.308 | 4.509 | 1,40x | 4,9 | 2,3 | 53,9 | 84,9 | 60,1 | 87,6 |
| GET /items/search | 5.780 | 4.114 | 1,40x | 5,4 | 3,0 | 54,5 | 83,3 | 60,4 | 86,9 |
| GET /stats | 238 | 239 | 0,99x | 270,8 | 269,0 | 349,9 | 434,4 | 386,8 | 536,1 |
| GET /cpu | 466 | 371 | 1,26x | 118,6 | 195,3 | 209,9 | 300,0 | 299,8 | 399,0 |
| POST /orders | 2.648 | 2.271 | 1,17x | 12,7 | 4,7 | 65,3 | 91,9 | 70,3 | 96,7 |
| POST /items | 5.640 | 3.629 | 1,55x | 5,5 | 3,1 | 55,2 | 86,1 | 61,4 | 89,9 |
| PUT /items/{id} | 5.827 | 3.897 | 1,50x | 5,4 | 2,9 | 54,8 | 85,1 | 60,4 | 88,2 |
| DELETE /items/{id} | 6.396 | 3.415 | 1,87x | 4,8 | 2,7 | 52,6 | 88,2 | 59,7 | 91,7 |
| GET /stores/{id}/sales-report | 599 | 539 | 1,11x | 101,6 | 102,0 | 170,3 | 205,7 | 194,7 | 297,8 |
| GET /reports/sales | 31 | 29 | 1,08x | 1.994,8 | 1.826,1 | 2.394,0 | 4.712,5 | 2.666,5 | 6.288,0 |
| POST /base64 | 8.601 | 7.062 | 1,22x | 3,3 | 1,8 | 51,5 | 77,9 | 60,0 | 82,2 |
| GET /factorial?n=1000 | 5.039 | 1.210 | 4,16x | 6,2 | 85,5 | 60,2 | 100,1 | 67,0 | 187,2 |

_Gecikmeler ms cinsinden._

### Kaynak kullanımı (yük altında)

| Endpoint | Go CPU % | Spring CPU % | Go RAM MiB | Spring RAM MiB | Go RAM tepe | Spring RAM tepe | DB CPU % (Go turu) | DB CPU % (Spring turu) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GET /health | 97 | 97 | 19 | 673 | 21 | 674 | 4 | 3 |
| GET /items | 94 | 96 | 20 | 673 | 21 | 674 | 79 | 71 |
| GET /items/{id} | 96 | 96 | 18 | 674 | 19 | 675 | 69 | 45 |
| GET /items/search | 96 | 96 | 19 | 674 | 20 | 675 | 175 | 112 |
| GET /stats | 13 | 16 | 20 | 673 | 21 | 674 | 766 | 767 |
| GET /cpu | 93 | 94 | 19 | 674 | 19 | 675 | 3 | 3 |
| POST /orders | 94 | 96 | 19 | 674 | 19 | 675 | 99 | 78 |
| POST /items | 96 | 96 | 18 | 675 | 19 | 676 | 94 | 63 |
| PUT /items/{id} | 95 | 95 | 18 | 675 | 19 | 676 | 92 | 64 |
| DELETE /items/{id} | 96 | 95 | 19 | 679 | 20 | 680 | 84 | 39 |
| GET /stores/{id}/sales-report | 94 | 96 | 30 | 679 | 33 | 679 | 73 | 81 |
| GET /reports/sales | 53 | 54 | 82 | 653 | 100 | 686 | 792 | 739 |
| POST /base64 | 96 | 96 | 29 | 504 | 65 | 505 | 3 | 3 |
| GET /factorial?n=1000 | 95 | 95 | 27 | 511 | 28 | 530 | 3 | 3 |

### Veri bekleme süresi ve uygulama içi süre (sunucu tarafı, istek başına ortalama ms)

| Endpoint | Go veri ms | Go uygulama ms | Go veri % | Spring veri ms | Spring uygulama ms | Spring veri % |
|---|---:|---:|---:|---:|---:|---:|
| GET /health | 0,000 | 0,010 | 0 | 0,000 | 0,027 | 0 |
| GET /items | 12,745 | 0,018 | 100 | 4,580 | 0,082 | 98 |
| GET /items/{id} | 7,650 | 0,009 | 100 | 2,726 | 0,054 | 98 |
| GET /items/search | 8,522 | 0,013 | 100 | 4,026 | 0,071 | 98 |
| GET /stats | 266,413 | 0,009 | 100 | 264,204 | 0,053 | 100 |
| GET /cpu | 0,000 | 8,752 | 0 | 0,000 | 51,749 | 0 |
| POST /orders | 22,048 | 0,028 | 100 | 12,984 | 0,147 | 99 |
| POST /items | 8,513 | 0,022 | 100 | 5,208 | 0,116 | 98 |
| PUT /items/{id} | 8,201 | 0,021 | 100 | 3,620 | 0,129 | 97 |
| DELETE /items/{id} | 7,166 | 0,006 | 100 | 4,488 | 0,848 | 84 |
| GET /stores/{id}/sales-report | 93,076 | 1,306 | 99 | 66,330 | 5,447 | 92 |
| GET /reports/sales | 2.006,437 | 0,202 | 100 | 2.138,403 | 0,396 | 100 |
| POST /base64 | 0,000 | 0,099 | 0 | 0,000 | 0,065 | 0 |
| GET /factorial?n=1000 | 0,000 | 0,393 | 0 | 0,000 | 7,755 | 0 |

### Isınmasız tur (60 sn faz, ısınma yükü yok)

| Endpoint | Go rps | Spring rps | Go/Spring | Go ısınmasız/ısınmalı | Spring ısınmasız/ısınmalı | Go p99 | Spring p99 |
|---|---:|---:|---:|---:|---:|---:|---:|
| GET /health | 14.012 | 4.845 | 2,89x | 1,03x | 0,52x | 55,6 | 95,8 |
| GET /items | 4.138 | 2.596 | 1,59x | 1,05x | 0,73x | 63,8 | 98,5 |
| GET /items/{id} | 6.387 | 3.999 | 1,60x | 1,01x | 0,89x | 60,5 | 91,8 |
| GET /items/search | 5.929 | 3.959 | 1,50x | 1,03x | 0,96x | 60,7 | 88,5 |
| GET /stats | 243 | 242 | 1,01x | 1,02x | 1,01x | 385,4 | 509,5 |
| GET /cpu | 477 | 320 | 1,49x | 1,02x | 0,86x | 295,0 | 603,6 |
| POST /orders | 2.635 | 1.844 | 1,43x | 1,00x | 0,81x | 69,6 | 101,2 |
| POST /items | 5.811 | 3.598 | 1,62x | 1,03x | 0,99x | 60,7 | 89,8 |
| PUT /items/{id} | 5.727 | 3.694 | 1,55x | 0,98x | 0,95x | 61,0 | 89,2 |
| DELETE /items/{id} | 5.390 | 4.188 | 1,29x | 0,84x | 1,23x | 60,3 | 88,3 |
| GET /stores/{id}/sales-report | 602 | 273 | 2,20x | 1,01x | 0,51x | 183,2 | 906,3 |
| GET /reports/sales | 30 | 30 | 1,02x | 0,98x | 1,03x | 2.687,7 | 6.572,5 |
| POST /base64 | 8.769 | 6.140 | 1,43x | 1,02x | 0,87x | 59,8 | 88,2 |
| GET /factorial?n=1000 | 5.015 | 994 | 5,05x | 1,00x | 0,82x | 66,4 | 200,3 |

### CPU çalışma süresi (yük süresince harcanan toplam CPU)

| Endpoint | Go CPU sn | Spring CPU sn | Go ms/istek | Spring ms/istek | Spring/Go | Veri deposu CPU sn (Go turu) | Veri deposu CPU sn (Spring turu) |
|---|---:|---:|---:|---:|---:|---:|---:|
| GET /health | 20,1 | 20,0 | 0,073 | 0,108 | 1,47x | 0,7 | 0,7 |
| GET /items | 20,0 | 20,0 | 0,255 | 0,281 | 1,10x | 16,7 | 14,9 |
| GET /items/{id} | 20,1 | 20,0 | 0,159 | 0,222 | 1,40x | 14,3 | 9,5 |
| GET /items/search | 20,1 | 20,0 | 0,173 | 0,242 | 1,40x | 36,6 | 23,4 |
| GET /stats | 2,7 | 3,3 | 0,564 | 0,687 | 1,22x | 162,2 | 162,2 |
| GET /cpu | 20,2 | 20,3 | 2,153 | 2,706 | 1,26x | 0,6 | 0,6 |
| POST /orders | 20,1 | 20,1 | 0,379 | 0,441 | 1,16x | 21,1 | 16,6 |
| POST /items | 20,0 | 20,0 | 0,177 | 0,275 | 1,55x | 19,8 | 13,1 |
| PUT /items/{id} | 20,0 | 20,0 | 0,172 | 0,255 | 1,49x | 19,4 | 13,3 |
| DELETE /items/{id} | 20,1 | 20,1 | 0,157 | 0,292 | 1,86x | 17,3 | 8,6 |
| GET /stores/{id}/sales-report | 20,1 | 20,2 | 1,675 | 1,861 | 1,11x | 15,7 | 17,3 |
| GET /reports/sales | 11,3 | 11,8 | 17,212 | 18,842 | 1,09x | 170,4 | 160,9 |
| POST /base64 | 20,1 | 20,0 | 0,117 | 0,141 | 1,21x | 0,7 | 0,7 |
| GET /factorial?n=1000 | 20,1 | 20,0 | 0,199 | 0,825 | 4,14x | 0,6 | 0,6 |

### Verimlilik: CPU başına throughput

| Endpoint | Go rps / %CPU | Spring rps / %CPU |
|---|---:|---:|
| GET /health | 140,8 | 95,7 |
| GET /items | 41,6 | 37,1 |
| GET /items/{id} | 65,5 | 47,1 |
| GET /items/search | 60,4 | 42,9 |
| GET /stats | 18,5 | 15,2 |
| GET /cpu | 5,0 | 3,9 |
| POST /orders | 28,1 | 23,7 |
| POST /items | 59,0 | 37,9 |
| PUT /items/{id} | 61,2 | 40,9 |
| DELETE /items/{id} | 67,0 | 36,0 |
| GET /stores/{id}/sales-report | 6,4 | 5,6 |
| GET /reports/sales | 0,6 | 0,5 |
| POST /base64 | 89,6 | 73,6 |
| GET /factorial?n=1000 | 53,1 | 12,8 |

### Hata oranı ve tur farkı

| Endpoint | Go hata % | Spring hata % | Go rps (min–maks tur) | Spring rps (min–maks tur) |
|---|---:|---:|---:|---:|
| GET /health | 0,00 | 0,00 | 13.584–13.688 | 8.924–9.713 |
| GET /items | 0,00 | 0,00 | 3.889–4.018 | 3.466–3.623 |
| GET /items/{id} | 0,00 | 0,00 | 6.223–6.510 | 4.491–4.712 |
| GET /items/search | 0,00 | 0,00 | 5.720–5.852 | 3.956–4.189 |
| GET /stats | 0,00 | 0,00 | 237–239 | 236–242 |
| GET /cpu | 0,00 | 0,00 | 464–473 | 358–376 |
| POST /orders | 0,00 | 0,00 | 2.618–2.669 | 1.959–2.282 |
| POST /items | 0,00 | 0,00 | 5.597–5.964 | 3.404–3.708 |
| PUT /items/{id} | 0,00 | 0,00 | 5.797–5.923 | 3.740–3.934 |
| DELETE /items/{id} | 0,00 | 0,00 | 6.266–6.410 | 2.682–3.496 |
| GET /stores/{id}/sales-report | 0,00 | 0,00 | 585–601 | 462–544 |
| GET /reports/sales | 0,00 | 0,00 | 31–31 | 29–29 |
| POST /base64 | 0,00 | 0,00 | 8.572–8.644 | 6.488–7.072 |
| GET /factorial?n=1000 | 0,00 | 0,00 | 4.927–5.136 | 1.155–1.243 |