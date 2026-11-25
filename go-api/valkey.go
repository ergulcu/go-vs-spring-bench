package main

// Valkey (Redis uyumlu, bellek içi) veri deposu modu: STORE=valkey.
// PostgreSQL modundaki endpoint'lerin aynı JSON'u döndüren karşılıkları; yazma işlemleri tek turda Lua betikleriyle yapılır.
//
// Veri modeli (scripts/bench.py tohumlar):
//   item:{id}        hash: name, category, price_cents, stock
//   items:ids        sorted set (skor = id): sayfalama
//   items:names      sorted set (skor 0, üye "lower(name):id"): önek araması (ZRANGEBYLEX)
//   items:seq        sayaç (sonraki kimlik)
//   store:{id}       hash: name, city        stores:ids  sorted set
//   sales:{storeId}  list: "epochSaniye|adet|tutarKuruş"
//   order:{id}       hash;  orders:seq sayaç
//
// /stats bu modda yoktur: SQL GROUP BY'ın bellek içi depoda doğal bir karşılığı yok.
// Süre ölçümü (timing.go): veri deposuna giden her çağrı track() ile sarılır.

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

var rdb *redis.Client

var (
	createScript = redis.NewScript(`
local id = redis.call('INCR', 'items:seq')
redis.call('HSET', 'item:' .. id, 'name', ARGV[1], 'category', ARGV[2], 'price_cents', ARGV[3], 'stock', ARGV[4])
redis.call('ZADD', 'items:ids', id, id)
redis.call('ZADD', 'items:names', 0, string.lower(ARGV[1]) .. ':' .. id)
return id`)

	updateScript = redis.NewScript(`
local key = 'item:' .. ARGV[1]
if redis.call('EXISTS', key) == 0 then return false end
redis.call('HSET', key, 'price_cents', ARGV[2], 'stock', ARGV[3])
return redis.call('HMGET', key, 'name', 'category', 'price_cents', 'stock')`)

	deleteScript = redis.NewScript(`
local key = 'item:' .. ARGV[1]
local name = redis.call('HGET', key, 'name')
if not name then return 0 end
redis.call('DEL', key)
redis.call('ZREM', 'items:ids', ARGV[1])
redis.call('ZREM', 'items:names', string.lower(name) .. ':' .. ARGV[1])
return 1`)

	orderScript = redis.NewScript(`
local key = 'item:' .. ARGV[1]
local stock = redis.call('HGET', key, 'stock')
if not stock or tonumber(stock) < tonumber(ARGV[2]) then return {-1, 0} end
redis.call('HINCRBY', key, 'stock', -tonumber(ARGV[2]))
local total = tonumber(redis.call('HGET', key, 'price_cents')) * tonumber(ARGV[2])
local oid = redis.call('INCR', 'orders:seq')
redis.call('HSET', 'order:' .. oid, 'item_id', ARGV[1], 'quantity', ARGV[2], 'total_cents', total)
return {oid, total}`)

	// Gün/ay toplamları Valkey İÇİNDE hesaplanır (SQL GROUP BY'ın karşılığı). Komutlar tek iş parçacığında yürüdüğünden
	// bu betik çalışırken sunucu başka isteğe bakmaz.
	// Çıktı, her mağaza için: [id, gunSayisi, (tarih, adet, birim, tutar)*, ayS, (ay, adet, birim, tutar)*]
	salesAggScript = redis.NewScript(`
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
return out`)
)

func initValkey() {
	addr := os.Getenv("VALKEY_ADDR")
	if addr == "" {
		addr = "bench-valkey:6379"
	}
	// PostgreSQL modundaki havuzla aynı boyut (20).
	// Zaman aşımları bilerek bol (Spring tarafındaki Jedis ile aynı, 30 sn): doygun Lua betiği kuyruğunda bekleyen istekler zaman aşımına düşmesin.
	rdb = redis.NewClient(&redis.Options{Addr: addr, PoolSize: 20, MinIdleConns: 20,
		DialTimeout: 5 * time.Second, ReadTimeout: 30 * time.Second, WriteTimeout: 30 * time.Second})
	if err := rdb.Ping(context.Background()).Err(); err != nil {
		log.Fatal(err)
	}
}

func registerValkey(mux *http.ServeMux) {
	mux.HandleFunc("GET /items", vListItems)
	mux.HandleFunc("GET /items/search", vSearchItems)
	mux.HandleFunc("GET /items/{id}", vGetItem)
	mux.HandleFunc("POST /items", vCreateItem)
	mux.HandleFunc("PUT /items/{id}", vUpdateItem)
	mux.HandleFunc("DELETE /items/{id}", vDeleteItem)
	mux.HandleFunc("POST /orders", vCreateOrder)
	mux.HandleFunc("GET /stores/{id}/sales-report", vStoreSalesReport)
	mux.HandleFunc("GET /reports/sales", vAllSalesReport)
}

// itemFromVals: HMGET name, category, price_cents, stock -> Item
func itemFromVals(id int64, v []interface{}) (Item, bool) {
	if len(v) < 4 || v[0] == nil {
		return Item{}, false
	}
	s := func(x interface{}) string { str, _ := x.(string); return str }
	price, _ := strconv.ParseInt(s(v[2]), 10, 32)
	stock, _ := strconv.ParseInt(s(v[3]), 10, 32)
	return Item{ID: id, Name: s(v[0]), Category: s(v[1]), PriceCents: int32(price), Stock: int32(stock)}, true
}

// fetchItems: kimlik listesi için tek pipeline ile HMGET (çağıran taraf süre ölçümünü yapar).
func fetchItems(ctx context.Context, ids []string) ([]Item, error) {
	items := make([]Item, 0, len(ids))
	if len(ids) == 0 {
		return items, nil
	}
	pipe := rdb.Pipeline()
	cmds := make([]*redis.SliceCmd, len(ids))
	for i, id := range ids {
		cmds[i] = pipe.HMGet(ctx, "item:"+id, "name", "category", "price_cents", "stock")
	}
	if _, err := pipe.Exec(ctx); err != nil {
		return nil, err
	}
	for i, c := range cmds {
		id, _ := strconv.ParseInt(ids[i], 10, 64)
		if it, ok := itemFromVals(id, c.Val()); ok {
			items = append(items, it)
		}
	}
	return items, nil
}

func vListItems(w http.ResponseWriter, r *http.Request) {
	after, _ := strconv.ParseInt(r.URL.Query().Get("after"), 10, 64)
	limit, err := strconv.Atoi(r.URL.Query().Get("limit"))
	if err != nil || limit < 1 || limit > 100 {
		limit = 50
	}
	ctx := r.Context()
	done := track(ctx)
	ids, err := rdb.ZRangeByScore(ctx, "items:ids", &redis.ZRangeBy{
		Min: "(" + strconv.FormatInt(after, 10), Max: "+inf", Offset: 0, Count: int64(limit)}).Result()
	if err != nil {
		done()
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	items, err := fetchItems(ctx, ids)
	done()
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, items)
}

func vGetItem(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		fail(w, http.StatusBadRequest, "bad id")
		return
	}
	done := track(r.Context())
	vals, err := rdb.HMGet(r.Context(), "item:"+strconv.FormatInt(id, 10), "name", "category", "price_cents", "stock").Result()
	done()
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	it, ok := itemFromVals(id, vals)
	if !ok {
		fail(w, http.StatusNotFound, "not found")
		return
	}
	writeJSON(w, http.StatusOK, it)
}

func vCreateItem(w http.ResponseWriter, r *http.Request) {
	var in NewItem
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.Name == "" {
		fail(w, http.StatusBadRequest, "bad body")
		return
	}
	done := track(r.Context())
	id, err := createScript.Run(r.Context(), rdb, nil, in.Name, in.Category, in.PriceCents, in.Stock).Int64()
	done()
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, Item{ID: id, Name: in.Name, Category: in.Category, PriceCents: in.PriceCents, Stock: in.Stock})
}

func vUpdateItem(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		fail(w, http.StatusBadRequest, "bad id")
		return
	}
	var in UpdateItem
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		fail(w, http.StatusBadRequest, "bad body")
		return
	}
	done := track(r.Context())
	res, err := updateScript.Run(r.Context(), rdb, nil, id, in.PriceCents, in.Stock).Slice()
	done()
	if errors.Is(err, redis.Nil) {
		fail(w, http.StatusNotFound, "not found")
		return
	}
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	it, ok := itemFromVals(id, res)
	if !ok {
		fail(w, http.StatusNotFound, "not found")
		return
	}
	writeJSON(w, http.StatusOK, it)
}

func vDeleteItem(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		fail(w, http.StatusBadRequest, "bad id")
		return
	}
	done := track(r.Context())
	n, err := deleteScript.Run(r.Context(), rdb, nil, id).Int64()
	done()
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	if n == 0 {
		fail(w, http.StatusNotFound, "not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// GET /items/search?q= - lower(name) önek araması: ZRANGEBYLEX, sonra kimliğe göre sıralı (PostgreSQL: ORDER BY id LIMIT 20)
func vSearchItems(w http.ResponseWriter, r *http.Request) {
	q := strings.ToLower(r.URL.Query().Get("q"))
	if q == "" {
		fail(w, http.StatusBadRequest, "q required")
		return
	}
	ctx := r.Context()
	done := track(ctx)
	members, err := rdb.ZRangeByLex(ctx, "items:names", &redis.ZRangeBy{Min: "[" + q, Max: "[" + q + "\xff", Offset: 0, Count: 20}).Result()
	if err != nil {
		done()
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	nums := make([]int64, 0, len(members))
	for _, m := range members {
		if i := strings.LastIndexByte(m, ':'); i >= 0 {
			if id, err := strconv.ParseInt(m[i+1:], 10, 64); err == nil {
				nums = append(nums, id)
			}
		}
	}
	sort.Slice(nums, func(a, b int) bool { return nums[a] < nums[b] })
	ids := make([]string, len(nums))
	for i, id := range nums {
		ids[i] = strconv.FormatInt(id, 10)
	}
	items, err := fetchItems(ctx, ids)
	done()
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, items)
}

func vCreateOrder(w http.ResponseWriter, r *http.Request) {
	var in NewOrder
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.Quantity < 1 {
		fail(w, http.StatusBadRequest, "bad body")
		return
	}
	done := track(r.Context())
	res, err := orderScript.Run(r.Context(), rdb, nil, in.ItemID, in.Quantity).Int64Slice()
	done()
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	if len(res) < 2 || res[0] < 0 {
		fail(w, http.StatusConflict, "no stock or item")
		return
	}
	writeJSON(w, http.StatusCreated, map[string]int64{"order_id": res[0], "total_cents": res[1]})
}

// satır: "epochSaniye|adet|tutar" -> agg.add (günlük/aylık toplamlar uygulama kodunda)
func addSale(a *agg, row string) {
	i := strings.IndexByte(row, '|')
	j := strings.LastIndexByte(row, '|')
	if i < 0 || j <= i {
		return
	}
	sec, _ := strconv.ParseInt(row[:i], 10, 64)
	qty, _ := strconv.ParseInt(row[i+1:j], 10, 32)
	amount, _ := strconv.ParseInt(row[j+1:], 10, 64)
	a.add(time.Unix(sec, 0).UTC(), int32(qty), amount)
}

// GET /stores/{id}/sales-report - satırlar Valkey'den okunur (veri süresi), toplamalar UYGULAMA KODUNDA yapılır.
func vStoreSalesReport(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 32)
	if err != nil {
		fail(w, http.StatusBadRequest, "bad id")
		return
	}
	ctx := r.Context()
	sid := strconv.FormatInt(id, 10)
	done := track(ctx)
	meta, err := rdb.HMGet(ctx, "store:"+sid, "name", "city").Result()
	if err != nil {
		done()
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	if len(meta) < 2 || meta[0] == nil {
		done()
		fail(w, http.StatusNotFound, "not found")
		return
	}
	rows, err := rdb.LRange(ctx, "sales:"+sid, 0, -1).Result()
	done()
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	a := newAgg()
	for _, row := range rows {
		addSale(a, row)
	}
	name, _ := meta[0].(string)
	city, _ := meta[1].(string)
	writeJSON(w, http.StatusOK, a.report(int32(id), name, city, true))
}

// GET /reports/sales - günlük/aylık toplamlar Valkey İÇİNDE (Lua) hesaplanır; uygulama yalnızca hazır toplamları rapora dizer.
func vAllSalesReport(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	done := track(ctx)
	ids, err := rdb.ZRange(ctx, "stores:ids", 0, -1).Result()
	if err != nil {
		done()
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	pipe := rdb.Pipeline()
	metas := make([]*redis.SliceCmd, len(ids))
	for i, id := range ids {
		metas[i] = pipe.HMGet(ctx, "store:"+id, "name", "city")
	}
	if _, err := pipe.Exec(ctx); err != nil {
		done()
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	args := make([]interface{}, len(ids))
	for i, id := range ids {
		args[i] = id
	}
	res, err := salesAggScript.Run(ctx, rdb, nil, args...).Slice()
	done()
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	pos := 0
	nextInt := func() int64 { v, _ := res[pos].(int64); pos++; return v }
	nextStr := func() string { v, _ := res[pos].(string); pos++; return v }
	out := make([]StoreReport, 0, len(ids))
	for i := range ids {
		sid := int32(nextInt())
		days := make([]DayRow, int(nextInt()))
		for k := range days {
			days[k].Date = nextStr()
			days[k].Orders = nextInt()
			days[k].Units = nextInt()
			days[k].Revenue = nextInt()
		}
		months := make([]MonthRow, int(nextInt()))
		for k := range months {
			months[k].Month = nextStr()
			months[k].Orders = nextInt()
			months[k].Units = nextInt()
			months[k].Revenue = nextInt()
		}
		m := metas[i].Val()
		name, _ := m[0].(string)
		city, _ := m[1].(string)
		out = append(out, buildReport(sid, name, city, days, months))
	}
	writeJSON(w, http.StatusOK, out)
}
