package main

// Sunucu tarafı süre ölçümü: her istekte "veri deposunu beklerken geçen süre" (data) ve toplam süre (total) ölçülür,
// yanıta `Server-Timing: data;dur=…, total;dur=…` başlığı olarak eklenir (milisaniye). k6 bunu okuyup rapora taşır.
//
//   data  : veri deposuna sorgu/komut gönderilmesinden, sonuçların uygulamaya okunup nesnelere çevrilmesine kadar geçen süre
//           (sürücü, ağ ve veri deposunda bekleme dahil; uygulamanın kendi mantığı dahil değil).
//   total : isteğin işleyiciye girmesinden yanıt başlığının yazılmasına kadar geçen süre (JSON gövdesinin yazılması dahil değil).
//   uygulama içi süre = total - data.

import (
	"context"
	"fmt"
	"net/http"
	"time"
)

type reqTimer struct{ data time.Duration }

type timerKey struct{}

// track, veri erişiminin başında çağrılır; dönen fonksiyon bitişte çağrılır.
func track(ctx context.Context) func() {
	t, _ := ctx.Value(timerKey{}).(*reqTimer)
	if t == nil {
		return func() {}
	}
	start := time.Now()
	return func() { t.data += time.Since(start) }
}

type timingWriter struct {
	http.ResponseWriter
	t     *reqTimer
	start time.Time
	wrote bool
}

func (w *timingWriter) WriteHeader(code int) {
	if !w.wrote {
		w.wrote = true
		w.Header().Set("Server-Timing", fmt.Sprintf("data;dur=%.3f, total;dur=%.3f",
			float64(w.t.data.Microseconds())/1000, float64(time.Since(w.start).Microseconds())/1000))
	}
	w.ResponseWriter.WriteHeader(code)
}

func (w *timingWriter) Write(b []byte) (int, error) {
	if !w.wrote {
		w.WriteHeader(http.StatusOK)
	}
	return w.ResponseWriter.Write(b)
}

func withTiming(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t := &reqTimer{}
		ctx := context.WithValue(r.Context(), timerKey{}, t)
		next.ServeHTTP(&timingWriter{ResponseWriter: w, t: t, start: time.Now()}, r.WithContext(ctx))
	})
}
