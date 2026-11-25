package bench;

import bench.ApiController.Agg;
import bench.ApiController.DayRow;
import bench.ApiController.Item;
import bench.ApiController.MonthRow;
import bench.ApiController.NewItem;
import bench.ApiController.NewOrder;
import bench.ApiController.StoreReport;
import bench.ApiController.UpdateItem;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import redis.clients.jedis.Jedis;
import redis.clients.jedis.JedisPool;
import redis.clients.jedis.Pipeline;
import redis.clients.jedis.Response;
import redis.clients.jedis.util.SafeEncoder;

/**
 * STORE=valkey: PostgreSQL modundaki endpoint'lerin aynı JSON'u döndüren, bellek içi veri deposu (Valkey) karşılıkları.
 * Veri modeli ve Lua betikleri go-api/valkey.go ile aynıdır. /stats bu modda yoktur.
 * Süre ölçümü (Timing): veri deposuna giden her çağrı Timing.get/run ile sarılır.
 */
@RestController
@Profile("valkey")
public class ValkeyController {

    private static final String CREATE = """
            local id = redis.call('INCR', 'items:seq')
            redis.call('HSET', 'item:' .. id, 'name', ARGV[1], 'category', ARGV[2], 'price_cents', ARGV[3], 'stock', ARGV[4])
            redis.call('ZADD', 'items:ids', id, id)
            redis.call('ZADD', 'items:names', 0, string.lower(ARGV[1]) .. ':' .. id)
            return id""";

    private static final String UPDATE = """
            local key = 'item:' .. ARGV[1]
            if redis.call('EXISTS', key) == 0 then return false end
            redis.call('HSET', key, 'price_cents', ARGV[2], 'stock', ARGV[3])
            return redis.call('HMGET', key, 'name', 'category', 'price_cents', 'stock')""";

    private static final String DELETE = """
            local key = 'item:' .. ARGV[1]
            local name = redis.call('HGET', key, 'name')
            if not name then return 0 end
            redis.call('DEL', key)
            redis.call('ZREM', 'items:ids', ARGV[1])
            redis.call('ZREM', 'items:names', string.lower(name) .. ':' .. ARGV[1])
            return 1""";

    private static final String ORDER = """
            local key = 'item:' .. ARGV[1]
            local stock = redis.call('HGET', key, 'stock')
            if not stock or tonumber(stock) < tonumber(ARGV[2]) then return {-1, 0} end
            redis.call('HINCRBY', key, 'stock', -tonumber(ARGV[2]))
            local total = tonumber(redis.call('HGET', key, 'price_cents')) * tonumber(ARGV[2])
            local oid = redis.call('INCR', 'orders:seq')
            redis.call('HSET', 'order:' .. oid, 'item_id', ARGV[1], 'quantity', ARGV[2], 'total_cents', total)
            return {oid, total}""";

    // Gün/ay toplamları Valkey İÇİNDE hesaplanır (SQL GROUP BY'ın karşılığı); go-api/valkey.go ile aynı betik.
    // Çıktı, her mağaza için: [id, gunSayisi, (tarih, adet, birim, tutar)*, ayS, (ay, adet, birim, tutar)*]
    private static final String SALES_AGG = """
            local function civil(z)
              z = z + 719468
              local era = math.floor(z / 146097)
              local doe = z - era * 146097
              local yoe = math.floor((doe - math.floor(doe / 1460) + math.floor(doe / 36524) - math.floor(doe / 146096)) / 365)
              local y = yoe + era * 400
              local doy = doe - (365 * yoe + math.floor(yoe / 4) - math.floor(yoe / 100))
              local mp = math.floor((5 * doy + 2) / 153)
              local d = doy - math.floor((153 * mp + 2) / 5) + 1
              local m = mp < 10 and mp + 3 or mp - 9
              if m <= 2 then y = y + 1 end
              return y, m, d
            end
            local out = {}
            for i = 1, #ARGV do
              local sid = ARGV[i]
              local rows = redis.call('LRANGE', 'sales:' .. sid, 0, -1)
              local days = {}
              for _, row in ipairs(rows) do
                local ts, qty, amt = string.match(row, '^(%d+)|(%d+)|(%d+)$')
                local dn = math.floor(tonumber(ts) / 86400)
                local d = days[dn]
                if not d then d = {0, 0, 0}; days[dn] = d end
                d[1] = d[1] + 1
                d[2] = d[2] + tonumber(qty)
                d[3] = d[3] + tonumber(amt)
              end
              local dkeys = {}
              for k in pairs(days) do dkeys[#dkeys + 1] = k end
              table.sort(dkeys)
              out[#out + 1] = tonumber(sid)
              out[#out + 1] = #dkeys
              local mon, mkeys = {}, {}
              for _, dn in ipairs(dkeys) do
                local y, m, d = civil(dn)
                local v = days[dn]
                out[#out + 1] = string.format('%04d-%02d-%02d', y, m, d)
                out[#out + 1] = v[1]; out[#out + 1] = v[2]; out[#out + 1] = v[3]
                local mk = y * 12 + (m - 1)
                local mm = mon[mk]
                if not mm then mm = {string.format('%04d-%02d', y, m), 0, 0, 0}; mon[mk] = mm; mkeys[#mkeys + 1] = mk end
                mm[2] = mm[2] + v[1]; mm[3] = mm[3] + v[2]; mm[4] = mm[4] + v[3]
              end
              out[#out + 1] = #mkeys
              for _, mk in ipairs(mkeys) do
                local mm = mon[mk]
                out[#out + 1] = mm[1]; out[#out + 1] = mm[2]; out[#out + 1] = mm[3]; out[#out + 1] = mm[4]
              end
            end
            return out""";

    private static final String[] ITEM_FIELDS = {"name", "category", "price_cents", "stock"};

    private final JedisPool pool;
    private final String createSha;
    private final String updateSha;
    private final String deleteSha;
    private final String orderSha;
    private final String salesAggSha;

    public ValkeyController(JedisPool pool) {
        this.pool = pool;
        try (Jedis j = pool.getResource()) {
            createSha = j.scriptLoad(CREATE);
            updateSha = j.scriptLoad(UPDATE);
            deleteSha = j.scriptLoad(DELETE);
            orderSha = j.scriptLoad(ORDER);
            salesAggSha = j.scriptLoad(SALES_AGG);
        }
    }

    private static Item itemFrom(long id, List<String> v) {
        if (v == null || v.size() < 4 || v.get(0) == null) {
            return null;
        }
        return new Item(id, v.get(0), v.get(1), Integer.parseInt(v.get(2)), Integer.parseInt(v.get(3)));
    }

    /** Kimlik listesi için tek pipeline ile HMGET (çağıran taraf süre ölçümünü yapar). */
    private static List<Item> fetchItems(Jedis j, List<String> ids) {
        List<Item> items = new ArrayList<>(ids.size());
        if (ids.isEmpty()) {
            return items;
        }
        Pipeline p = j.pipelined();
        List<Response<List<String>>> rs = new ArrayList<>(ids.size());
        for (String id : ids) {
            rs.add(p.hmget("item:" + id, ITEM_FIELDS));
        }
        p.sync();
        for (int i = 0; i < ids.size(); i++) {
            Item it = itemFrom(Long.parseLong(ids.get(i)), rs.get(i).get());
            if (it != null) {
                items.add(it);
            }
        }
        return items;
    }

    private static String str(Object o) {
        return o == null ? null : (o instanceof byte[] b ? SafeEncoder.encode(b) : o.toString());
    }

    private static ResponseEntity<?> notFound() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", "not found"));
    }

    // 2. GET /items?after=&limit= - sorted set üzerinde keyset sayfalama
    @GetMapping("/items")
    public List<Item> list(@RequestParam(defaultValue = "0") long after,
                           @RequestParam(defaultValue = "50") int limit) {
        int lim = (limit < 1 || limit > 100) ? 50 : limit;
        return Timing.get(() -> {
            try (Jedis j = pool.getResource()) {
                return fetchItems(j, j.zrangeByScore("items:ids", "(" + after, "+inf", 0, lim));
            }
        });
    }

    // 3. GET /items/{id}
    @GetMapping("/items/{id}")
    public ResponseEntity<?> get(@PathVariable long id) {
        Item it = Timing.get(() -> {
            try (Jedis j = pool.getResource()) {
                return itemFrom(id, j.hmget("item:" + id, ITEM_FIELDS));
            }
        });
        return it == null ? notFound() : ResponseEntity.ok(it);
    }

    // 4. POST /items
    @PostMapping("/items")
    public ResponseEntity<?> create(@RequestBody NewItem in) {
        if (in.name() == null || in.name().isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", "bad body"));
        }
        long id = Timing.get(() -> {
            try (Jedis j = pool.getResource()) {
                return (Long) j.evalsha(createSha, Collections.emptyList(), List.of(
                        in.name(), in.category(), String.valueOf(in.priceCents()), String.valueOf(in.stock())));
            }
        });
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new Item(id, in.name(), in.category(), in.priceCents(), in.stock()));
    }

    // 5. PUT /items/{id}
    @PutMapping("/items/{id}")
    public ResponseEntity<?> update(@PathVariable long id, @RequestBody UpdateItem in) {
        Object r = Timing.get(() -> {
            try (Jedis j = pool.getResource()) {
                return j.evalsha(updateSha, Collections.emptyList(), List.of(
                        String.valueOf(id), String.valueOf(in.priceCents()), String.valueOf(in.stock())));
            }
        });
        if (!(r instanceof List<?> raw)) {
            return notFound();
        }
        List<String> vals = new ArrayList<>(raw.size());
        for (Object o : raw) {
            vals.add(str(o));
        }
        Item it = itemFrom(id, vals);
        return it == null ? notFound() : ResponseEntity.ok(it);
    }

    // 6. DELETE /items/{id}
    @DeleteMapping("/items/{id}")
    public ResponseEntity<?> delete(@PathVariable long id, HttpServletResponse res) {
        Object r = Timing.get(() -> {
            try (Jedis j = pool.getResource()) {
                return j.evalsha(deleteSha, Collections.emptyList(), List.of(String.valueOf(id)));
            }
        });
        res.setHeader("Server-Timing", Timing.header()); // 204 yanıtı gövdesiz: ResponseBodyAdvice çalışmaz, başlık burada yazılır
        return ((Long) r) == 0 ? notFound() : ResponseEntity.noContent().build();
    }

    // 7. GET /items/search?q= - lower(name) önek araması: ZRANGEBYLEX, sonra kimliğe göre sıralı
    @GetMapping("/items/search")
    public ResponseEntity<?> search(@RequestParam(defaultValue = "") String q) {
        if (q.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", "q required"));
        }
        String lower = q.toLowerCase();
        List<Item> items = Timing.get(() -> {
            try (Jedis j = pool.getResource()) {
                List<String> members = j.zrangeByLex("items:names", "[" + lower, "[" + lower + "￿", 0, 20);
                List<Long> nums = new ArrayList<>(members.size());
                for (String m : members) {
                    int i = m.lastIndexOf(':');
                    if (i >= 0) {
                        nums.add(Long.parseLong(m.substring(i + 1)));
                    }
                }
                Collections.sort(nums);
                List<String> ids = new ArrayList<>(nums.size());
                for (Long id : nums) {
                    ids.add(String.valueOf(id));
                }
                return fetchItems(j, ids);
            }
        });
        return ResponseEntity.ok(items);
    }

    // 9. POST /orders - Lua betiği: stok düş + sipariş ekle (tek atomik adım)
    @PostMapping("/orders")
    public ResponseEntity<?> order(@RequestBody NewOrder in) {
        if (in.quantity() < 1) {
            return ResponseEntity.badRequest().body(Map.of("error", "bad body"));
        }
        List<?> res = Timing.get(() -> {
            try (Jedis j = pool.getResource()) {
                return (List<?>) j.evalsha(orderSha, Collections.emptyList(),
                        List.of(String.valueOf(in.itemId()), String.valueOf(in.quantity())));
            }
        });
        long oid = (Long) res.get(0);
        if (oid < 0) {
            return ResponseEntity.status(HttpStatus.CONFLICT).body(Map.of("error", "no stock or item"));
        }
        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of("order_id", oid, "total_cents", (Long) res.get(1)));
    }

    /** "epochSaniye|adet|tutar" satırını biriktiriciye ekler (günlük/aylık toplamlar uygulama kodunda). */
    private static void addSale(Agg agg, String row) {
        int i = row.indexOf('|');
        int k = row.lastIndexOf('|');
        if (i < 0 || k <= i) {
            return;
        }
        long sec = Long.parseLong(row, 0, i, 10);
        int qty = Integer.parseInt(row, i + 1, k, 10);
        long amount = Long.parseLong(row, k + 1, row.length(), 10);
        agg.add(LocalDateTime.ofEpochSecond(sec, 0, ZoneOffset.UTC), qty, amount);
    }

    // 11. GET /stores/{id}/sales-report - satırlar Valkey'den okunur (veri süresi), toplamalar UYGULAMA KODUNDA yapılır
    @GetMapping("/stores/{id}/sales-report")
    public ResponseEntity<?> storeSalesReport(@PathVariable int id) {
        List<String> meta = Timing.get(() -> {
            try (Jedis j = pool.getResource()) {
                return j.hmget("store:" + id, "name", "city");
            }
        });
        if (meta == null || meta.size() < 2 || meta.get(0) == null) {
            return notFound();
        }
        List<String> rows = Timing.get(() -> {
            try (Jedis j = pool.getResource()) {
                return j.lrange("sales:" + id, 0, -1);
            }
        });
        Agg agg = new Agg();
        for (String row : rows) {
            addSale(agg, row);
        }
        return ResponseEntity.ok(agg.report(id, meta.get(0), meta.get(1), true));
    }

    // 12. GET /reports/sales - günlük/aylık toplamlar Valkey İÇİNDE (Lua) hesaplanır; uygulama yalnızca hazır toplamları rapora dizer
    @GetMapping("/reports/sales")
    public List<StoreReport> allSalesReport() {
        List<String> ids = new ArrayList<>();
        List<List<String>> metas = new ArrayList<>();
        Object[] holder = new Object[1];
        Timing.run(() -> {
            try (Jedis j = pool.getResource()) {
                ids.addAll(j.zrange("stores:ids", 0, -1));
                Pipeline p = j.pipelined();
                List<Response<List<String>>> rs = new ArrayList<>(ids.size());
                for (String id : ids) {
                    rs.add(p.hmget("store:" + id, "name", "city"));
                }
                p.sync();
                for (Response<List<String>> r : rs) {
                    metas.add(r.get());
                }
                holder[0] = j.evalsha(salesAggSha, Collections.emptyList(), ids);
            }
        });
        List<?> res = (List<?>) holder[0];
        int[] pos = {0};
        List<StoreReport> out = new ArrayList<>(ids.size());
        for (int i = 0; i < ids.size(); i++) {
            int sid = (int) (long) (Long) res.get(pos[0]++);
            int nd = (int) (long) (Long) res.get(pos[0]++);
            List<DayRow> days = new ArrayList<>(nd);
            for (int k = 0; k < nd; k++) {
                String date = (String) res.get(pos[0]++);
                long orders = (Long) res.get(pos[0]++);
                long units = (Long) res.get(pos[0]++);
                long revenue = (Long) res.get(pos[0]++);
                days.add(new DayRow(date, orders, units, revenue));
            }
            int nm = (int) (long) (Long) res.get(pos[0]++);
            List<MonthRow> months = new ArrayList<>(nm);
            for (int k = 0; k < nm; k++) {
                String month = (String) res.get(pos[0]++);
                long orders = (Long) res.get(pos[0]++);
                long units = (Long) res.get(pos[0]++);
                long revenue = (Long) res.get(pos[0]++);
                months.add(new MonthRow(month, orders, units, revenue, 0, null));
            }
            List<String> m = metas.get(i);
            out.add(ApiController.buildReport(sid, m.get(0), m.get(1), days, months));
        }
        return out;
    }
}
