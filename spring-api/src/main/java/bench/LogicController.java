package bench;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.math.BigInteger;
import java.util.Base64;
import java.util.Map;
import org.springframework.web.bind.annotation.*;

/** Veritabanısız mantık uç noktaları: hangi veri deposu seçilirse seçilsin (PostgreSQL ya da Valkey) aynıdır. */
@RestController
public class LogicController {

    // 1. GET /health - yalnızca uygulama: veri deposuna dokunmaz (canlılık). HTTP çerçevesinin ham maliyetini gösterir.
    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "UP");
    }

    // 10. GET /cpu?n= - veritabanısız, saf CPU işi (n'e kadar asal sayıları say)
    @GetMapping("/cpu")
    public Map<String, Integer> cpu(@RequestParam(defaultValue = "50000") int n) {
        int limit = (n < 2 || n > 200000) ? 50000 : n;
        int count = 0;
        for (int i = 2; i <= limit; i++) {
            boolean prime = true;
            for (int j = 2; j * j <= i; j++) {
                if (i % j == 0) {
                    prime = false;
                    break;
                }
            }
            if (prime) {
                count++;
            }
        }
        return Map.of("n", limit, "primes", count);
    }

    // ---- 13-14. Veritabanısız mantık uç noktaları ----

    public record B64Result(
            @JsonProperty("input_bytes") int inputBytes,
            @JsonProperty("encoded_bytes") int encodedBytes,
            String encoded) {}

    public record FactResult(
            int n,
            int digits,
            @JsonProperty("first_digits") String firstDigits,
            @JsonProperty("trailing_zeros") int trailingZeros) {}

    // 13. POST /base64 - isteğin gövdesini okur ve Base64'e çevirir (veritabanı yok)
    @PostMapping("/base64")
    public B64Result base64(@RequestBody byte[] body) {
        String enc = Base64.getEncoder().encodeToString(body);
        return new B64Result(body.length, enc.length(), enc);
    }

    // 14. GET /factorial?n= - n! değerini BigInteger ile hesaplar (veritabanı yok).
    // Bilerek sıralı çarpma: Go tarafındaki big.Int döngüsüyle aynı algoritma.
    @GetMapping("/factorial")
    public FactResult factorial(@RequestParam(defaultValue = "1000") int n) {
        int limit = (n < 1 || n > 5000) ? 1000 : n;
        BigInteger f = BigInteger.ONE;
        for (int i = 2; i <= limit; i++) {
            f = f.multiply(BigInteger.valueOf(i));
        }
        String s = f.toString();
        int end = s.length();
        while (end > 0 && s.charAt(end - 1) == '0') {
            end--;
        }
        return new FactResult(limit, s.length(), s.substring(0, Math.min(16, s.length())), s.length() - end);
    }
}
