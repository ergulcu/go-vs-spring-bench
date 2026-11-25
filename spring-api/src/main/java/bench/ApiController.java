package bench;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.bind.annotation.*;

@RestController
@Profile("!valkey") // STORE=valkey modunda bu PostgreSQL denetleyicisi kapalıdır; ValkeyController devreye girer
public class ApiController {

    public record Item(
            long id,
            String name,
            String category,
            @JsonProperty("price_cents") int priceCents,
            int stock) {}

    public record NewItem(
            String name,
            String category,
            @JsonProperty("price_cents") int priceCents,
            int stock) {}

    public record UpdateItem(
            @JsonProperty("price_cents") int priceCents,
            int stock) {}

    public record NewOrder(
            @JsonProperty("item_id") long itemId,
            int quantity) {}

    public record CategoryStat(
            String category,
            long count,
            @JsonProperty("avg_price_cents") double avgPrice,
            @JsonProperty("total_stock") long totalStock) {}

    private static final String ITEM_COLS = "id, name, category, price_cents, stock";

    private final JdbcClient jdbc;
    private final TransactionTemplate tx;

    public ApiController(JdbcClient jdbc, TransactionTemplate tx) {
        this.jdbc = jdbc;
        this.tx = tx;
    }

    private static Item mapItem(java.sql.ResultSet rs, int n) throws java.sql.SQLException {
        return new Item(rs.getLong(1), rs.getString(2), rs.getString(3), rs.getInt(4), rs.getInt(5));
    }

    // 2. GET /items?after=&limit= - keyset sayfalama
    @GetMapping("/items")
    public List<Item> list(@RequestParam(defaultValue = "0") long after,
                           @RequestParam(defaultValue = "50") int limit) {
        int lim = (limit < 1 || limit > 100) ? 50 : limit;
        return Timing.get(() -> jdbc.sql("SELECT " + ITEM_COLS + " FROM items WHERE id > ? ORDER BY id LIMIT ?")
                .param(after).param(lim)
                .query(ApiController::mapItem).list());
    }

    // 3. GET /items/{id}
    @GetMapping("/items/{id}")
    public ResponseEntity<?> get(@PathVariable long id) {
        Optional<Item> it = Timing.get(() -> jdbc.sql("SELECT " + ITEM_COLS + " FROM items WHERE id = ?")
                .param(id).query(ApiController::mapItem).optional());
        return it.<ResponseEntity<?>>map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", "not found")));
    }

    // 4. POST /items
    @PostMapping("/items")
    public ResponseEntity<?> create(@RequestBody NewItem in) {
        if (in.name() == null || in.name().isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", "bad body"));
        }
        Item it = Timing.get(() -> jdbc.sql("INSERT INTO items (name, category, price_cents, stock) VALUES (?, ?, ?, ?) RETURNING " + ITEM_COLS)
                .param(in.name()).param(in.category()).param(in.priceCents()).param(in.stock())
                .query(ApiController::mapItem).single());
        return ResponseEntity.status(HttpStatus.CREATED).body(it);
    }

    // 5. PUT /items/{id}
    @PutMapping("/items/{id}")
    public ResponseEntity<?> update(@PathVariable long id, @RequestBody UpdateItem in) {
        Optional<Item> it = Timing.get(() -> jdbc.sql("UPDATE items SET price_cents = ?, stock = ?, updated_at = now() WHERE id = ? RETURNING " + ITEM_COLS)
                .param(in.priceCents()).param(in.stock()).param(id)
                .query(ApiController::mapItem).optional());
        return it.<ResponseEntity<?>>map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", "not found")));
    }

    // 6. DELETE /items/{id}
    @DeleteMapping("/items/{id}")
    public ResponseEntity<?> delete(@PathVariable long id, HttpServletResponse res) {
        int n = Timing.get(() -> jdbc.sql("DELETE FROM items WHERE id = ?").param(id).update());
        res.setHeader("Server-Timing", Timing.header()); // 204 yanıtı gövdesiz: ResponseBodyAdvice çalışmaz, başlık burada yazılır
        if (n == 0) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", "not found"));
        }
        return ResponseEntity.noContent().build();
    }

    // 7. GET /items/search?q= - lower(name) önek araması (indeksli)
    @GetMapping("/items/search")
    public ResponseEntity<?> search(@RequestParam(defaultValue = "") String q) {
        if (q.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", "q required"));
        }
        List<Item> items = Timing.get(() -> jdbc.sql("SELECT " + ITEM_COLS + " FROM items WHERE lower(name) LIKE ? ORDER BY id LIMIT 20")
                .param(q.toLowerCase() + "%")
                .query(ApiController::mapItem).list());
        return ResponseEntity.ok(items);
    }

    // 8. GET /stats - tüm tabloda gruplu toplama
    @GetMapping("/stats")
    public List<CategoryStat> stats() {
        return Timing.get(() -> jdbc.sql("SELECT category, count(*)::bigint, avg(price_cents)::float8, sum(stock)::bigint FROM items GROUP BY category ORDER BY category")
                .query((rs, n) -> new CategoryStat(rs.getString(1), rs.getLong(2), rs.getDouble(3), rs.getLong(4)))
                .list());
    }

    // 9. POST /orders - tek transaction: stok düş + sipariş ekle.
    // Transaction bilerek elle yönetilir (TransactionTemplate): başlatma, iki sorgu ve commit tek "veri erişimi" bloğu olarak ölçülür.
    @PostMapping("/orders")
    public ResponseEntity<?> order(@RequestBody NewOrder in) {
        if (in.quantity() < 1) {
            return ResponseEntity.badRequest().body(Map.of("error", "bad body"));
        }
        Map<String, Long> result = Timing.get(() -> tx.execute(status -> {
            Optional<Integer> price = jdbc.sql("UPDATE items SET stock = stock - ? WHERE id = ? AND stock >= ? RETURNING price_cents")
                    .param(in.quantity()).param(in.itemId()).param(in.quantity())
                    .query(Integer.class).optional();
            if (price.isEmpty()) {
                return null;
            }
            long total = (long) price.get() * in.quantity();
            long orderId = jdbc.sql("INSERT INTO orders (item_id, quantity, total_cents) VALUES (?, ?, ?) RETURNING id")
                    .param(in.itemId()).param(in.quantity()).param(total)
                    .query(Long.class).single();
            return Map.of("order_id", orderId, "total_cents", total);
        }));
        if (result == null) {
            return ResponseEntity.status(HttpStatus.CONFLICT).body(Map.of("error", "no stock or item"));
        }
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

    // ---- 11-12. Satış raporları: günlük ve aylık toplamlar SQL ile değil, uygulama kodunda hesaplanır ----

    public record DayRow(String date, long orders, long units, @JsonProperty("revenue_cents") long revenueCents) {}

    public record MonthRow(
            String month,
            long orders,
            long units,
            @JsonProperty("revenue_cents") long revenueCents,
            @JsonProperty("avg_order_cents") double avgOrderCents,
            @JsonProperty("growth_pct") Double growthPct) {} // bir önceki aya göre değişim; ilk ayda null

    public record StoreReport(
            @JsonProperty("store_id") int storeId,
            String name,
            String city,
            @JsonProperty("total_orders") long totalOrders,
            @JsonProperty("total_revenue_cents") long totalRevenueCents,
            @JsonProperty("avg_daily_revenue_cents") double avgDailyRevenueCents,
            @JsonProperty("best_day") DayRow bestDay,
            List<MonthRow> monthly,
            @JsonInclude(JsonInclude.Include.NON_NULL) List<DayRow> daily) {}

    static final class Bucket {
        long orders;
        long units;
        long revenue;
    }

    /** Bir mağazanın satış satırlarını gün ve ay anahtarlarına göre biriktirir. */
    static final class Agg {
        final Map<String, Bucket> daily = new HashMap<>();
        final Map<String, Bucket> monthly = new HashMap<>();

        void add(LocalDateTime t, int qty, long amount) {
            String day = t.toLocalDate().toString();
            String month = day.substring(0, 7);
            Bucket d = daily.computeIfAbsent(day, k -> new Bucket());
            d.orders++;
            d.units += qty;
            d.revenue += amount;
            Bucket m = monthly.computeIfAbsent(month, k -> new Bucket());
            m.orders++;
            m.units += qty;
            m.revenue += amount;
        }

        StoreReport report(int id, String name, String city, boolean withDaily) {
            List<String> days = new ArrayList<>(daily.keySet());
            Collections.sort(days);
            long totalOrders = 0;
            long totalRevenue = 0;
            DayRow best = null;
            List<DayRow> dailyRows = withDaily ? new ArrayList<>(days.size()) : null;
            for (String k : days) {
                Bucket b = daily.get(k);
                DayRow row = new DayRow(k, b.orders, b.units, b.revenue);
                totalOrders += b.orders;
                totalRevenue += b.revenue;
                if (best == null || row.revenueCents() > best.revenueCents()) {
                    best = row;
                }
                if (withDaily) {
                    dailyRows.add(row);
                }
            }
            double avgDaily = days.isEmpty() ? 0 : (double) totalRevenue / days.size();
            List<String> months = new ArrayList<>(monthly.keySet());
            Collections.sort(months);
            List<MonthRow> monthRows = new ArrayList<>(months.size());
            long prev = 0;
            for (int i = 0; i < months.size(); i++) {
                Bucket b = monthly.get(months.get(i));
                double avgOrder = b.orders > 0 ? (double) b.revenue / b.orders : 0;
                Double growth = (i > 0 && prev > 0) ? (double) (b.revenue - prev) / prev * 100 : null;
                prev = b.revenue;
                monthRows.add(new MonthRow(months.get(i), b.orders, b.units, b.revenue, avgOrder, growth));
            }
            return new StoreReport(id, name, city, totalOrders, totalRevenue, avgDaily, best, monthRows, dailyRows);
        }
    }

    record Store(int id, String name, String city) {}

    record SaleRow(LocalDateTime soldAt, int qty, long amount) {}

    // 11. GET /stores/{id}/sales-report - satırlar önce tamamen okunur (veri süresi), toplamalar sonra UYGULAMA KODUNDA yapılır
    @GetMapping("/stores/{id}/sales-report")
    public ResponseEntity<?> storeSalesReport(@PathVariable int id) {
        Optional<Store> store = Timing.get(() -> jdbc.sql("SELECT id, name, city FROM stores WHERE id = ?").param(id)
                .query((rs, n) -> new Store(rs.getInt(1), rs.getString(2), rs.getString(3))).optional());
        if (store.isEmpty()) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", "not found"));
        }
        List<SaleRow> rows = Timing.get(() -> jdbc.sql("SELECT sold_at, quantity, amount_cents FROM sales WHERE store_id = ?").param(id)
                .query((rs, n) -> new SaleRow(rs.getObject(1, LocalDateTime.class), rs.getInt(2), rs.getLong(3))).list());
        Agg agg = new Agg();
        for (SaleRow r : rows) {
            agg.add(r.soldAt(), r.qty(), r.amount());
        }
        Store st = store.get();
        return ResponseEntity.ok(agg.report(st.id(), st.name(), st.city(), true));
    }

    /** Gün ve ay toplamları hazırken (veri deposunda hesaplanmış) rapor alanlarını üretir: toplam, ortalama, en iyi gün, aylık büyüme. */
    static StoreReport buildReport(int id, String name, String city, List<DayRow> days, List<MonthRow> months) {
        long totalOrders = 0;
        long totalRevenue = 0;
        DayRow best = null;
        for (DayRow d : days) {
            totalOrders += d.orders();
            totalRevenue += d.revenueCents();
            if (best == null || d.revenueCents() > best.revenueCents()) {
                best = d;
            }
        }
        double avgDaily = days.isEmpty() ? 0 : (double) totalRevenue / days.size();
        List<MonthRow> out = new ArrayList<>(months.size());
        long prev = 0;
        for (int i = 0; i < months.size(); i++) {
            MonthRow m = months.get(i);
            double avgOrder = m.orders() > 0 ? (double) m.revenueCents() / m.orders() : 0;
            Double growth = (i > 0 && prev > 0) ? (double) (m.revenueCents() - prev) / prev * 100 : null;
            prev = m.revenueCents();
            out.add(new MonthRow(m.month(), m.orders(), m.units(), m.revenueCents(), avgOrder, growth));
        }
        return new StoreReport(id, name, city, totalOrders, totalRevenue, avgDaily, best, out, null);
    }

    // 12. GET /reports/sales - tüm mağazalar: günlük ve aylık toplamlar VERİTABANINDA (SQL GROUP BY) hesaplanır;
    // uygulama yalnızca hazır toplamları rapora dizer (en iyi gün, büyüme yüzdesi).
    @GetMapping("/reports/sales")
    public List<StoreReport> allSalesReport() {
        List<Store> stores = new ArrayList<>();
        Map<Integer, List<DayRow>> days = new HashMap<>();
        Map<Integer, List<MonthRow>> months = new HashMap<>();
        Timing.run(() -> {
            stores.addAll(jdbc.sql("SELECT id, name, city FROM stores ORDER BY id")
                    .query((rs, n) -> new Store(rs.getInt(1), rs.getString(2), rs.getString(3))).list());
            jdbc.sql("SELECT store_id, to_char(sold_at, 'YYYY-MM-DD'), count(*)::bigint, sum(quantity)::bigint, sum(amount_cents)::bigint "
                            + "FROM sales GROUP BY store_id, 2 ORDER BY store_id, 2")
                    .query((RowCallbackHandler) rs -> days.computeIfAbsent(rs.getInt(1), k -> new ArrayList<>())
                            .add(new DayRow(rs.getString(2), rs.getLong(3), rs.getLong(4), rs.getLong(5))));
            jdbc.sql("SELECT store_id, to_char(sold_at, 'YYYY-MM'), count(*)::bigint, sum(quantity)::bigint, sum(amount_cents)::bigint "
                            + "FROM sales GROUP BY store_id, 2 ORDER BY store_id, 2")
                    .query((RowCallbackHandler) rs -> months.computeIfAbsent(rs.getInt(1), k -> new ArrayList<>())
                            .add(new MonthRow(rs.getString(2), rs.getLong(3), rs.getLong(4), rs.getLong(5), 0, null)));
        });
        List<StoreReport> out = new ArrayList<>(stores.size());
        for (Store st : stores) {
            out.add(buildReport(st.id(), st.name(), st.city(),
                    days.getOrDefault(st.id(), List.of()), months.getOrDefault(st.id(), List.of())));
        }
        return out;
    }
}
