package bench;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.Locale;
import java.util.function.Supplier;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.MethodParameter;
import org.springframework.http.MediaType;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyAdvice;

/**
 * Sunucu tarafı süre ölçümü (go-api/timing.go ile aynı tanım). Her istekte "veri deposunu beklerken geçen süre" (data) ve
 * toplam süre (total) ölçülür, yanıta {@code Server-Timing: data;dur=…, total;dur=…} başlığı (ms) olarak eklenir.
 *
 * data : veri deposuna sorgu/komut gönderilmesinden, sonuçların uygulamaya okunup nesnelere çevrilmesine kadar geçen süre.
 * total: isteğin işleyiciye girmesinden yanıt gövdesinin yazılmaya başlamasına kadar geçen süre.
 * uygulama içi süre = total - data.
 */
public final class Timing {

    private static final ThreadLocal<long[]> T = new ThreadLocal<>(); // [0] başlangıç (ns), [1] veri süresi (ns)

    private Timing() {}

    static void begin() {
        T.set(new long[] {System.nanoTime(), 0});
    }

    static void end() {
        T.remove();
    }

    /** Veri erişimi yapan bir işi ölçerek çalıştırır ve sonucunu döndürür. */
    public static <R> R get(Supplier<R> s) {
        long[] t = T.get();
        long a = System.nanoTime();
        try {
            return s.get();
        } finally {
            if (t != null) {
                t[1] += System.nanoTime() - a;
            }
        }
    }

    /** Sonuç döndürmeyen veri erişimi işi. */
    public static void run(Runnable r) {
        long[] t = T.get();
        long a = System.nanoTime();
        try {
            r.run();
        } finally {
            if (t != null) {
                t[1] += System.nanoTime() - a;
            }
        }
    }

    static String header() {
        long[] t = T.get();
        if (t == null) {
            return null;
        }
        return String.format(Locale.ROOT, "data;dur=%.3f, total;dur=%.3f", t[1] / 1e6, (System.nanoTime() - t[0]) / 1e6);
    }

    @Configuration
    static class Web implements WebMvcConfigurer {
        @Override
        public void addInterceptors(InterceptorRegistry registry) {
            registry.addInterceptor(new HandlerInterceptor() {
                @Override
                public boolean preHandle(HttpServletRequest req, HttpServletResponse res, Object handler) {
                    begin();
                    return true;
                }

                @Override
                public void afterCompletion(HttpServletRequest req, HttpServletResponse res, Object handler, Exception ex) {
                    end();
                }
            });
        }
    }

    @ControllerAdvice
    static class Advice implements ResponseBodyAdvice<Object> {
        @Override
        public boolean supports(MethodParameter returnType, Class<? extends HttpMessageConverter<?>> converterType) {
            return true;
        }

        @Override
        public Object beforeBodyWrite(Object body, MethodParameter returnType, MediaType selectedContentType,
                                      Class<? extends HttpMessageConverter<?>> selectedConverterType,
                                      ServerHttpRequest request, ServerHttpResponse response) {
            String h = header();
            if (h != null) {
                response.getHeaders().set("Server-Timing", h);
            }
            return body;
        }
    }
}
