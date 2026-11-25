package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"log"
	"math/big"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Item struct {
	ID         int64  `json:"id"`
	Name       string `json:"name"`
	Category   string `json:"category"`
	PriceCents int32  `json:"price_cents"`
	Stock      int32  `json:"stock"`
}

type NewItem struct {
	Name       string `json:"name"`
	Category   string `json:"category"`
	PriceCents int32  `json:"price_cents"`
	Stock      int32  `json:"stock"`
}

type UpdateItem struct {
	PriceCents int32 `json:"price_cents"`
	Stock      int32 `json:"stock"`
}

type NewOrder struct {
	ItemID   int64 `json:"item_id"`
	Quantity int32 `json:"quantity"`
}

type CategoryStat struct {
	Category   string  `json:"category"`
	Count      int64   `json:"count"`
	AvgPrice   float64 `json:"avg_price_cents"`
	TotalStock int64   `json:"total_stock"`
}

const itemCols = "id, name, category, price_cents, stock"

var pool *pgxpool.Pool

func main() {
	mux := http.NewServeMux()
	// Veritabanısız mantık uç noktaları: her iki veri deposu modunda da aynı.
	mux.HandleFunc("GET /cpu", cpuWork)
	mux.HandleFunc("POST /base64", base64Work)
	mux.HandleFunc("GET /factorial", factorial)
	mux.HandleFunc("GET /health", health)

	if os.Getenv("STORE") == "valkey" {
		// Bellek içi veri deposu modu (valkey.go); PostgreSQL'e hiç bağlanılmaz.
		initValkey()
		registerValkey(mux)
	} else {
		dsn := os.Getenv("DATABASE_URL")
		cfg, err := pgxpool.ParseConfig(dsn)
		if err != nil {
			log.Fatal(err)
		}
		cfg.MaxConns = 20 // Spring tarafındaki Hikari havuzuyla aynı
		cfg.MinConns = 20
		pool, err = pgxpool.NewWithConfig(context.Background(), cfg)
		if err != nil {
			log.Fatal(err)
		}
		mux.HandleFunc("GET /items", listItems)
		mux.HandleFunc("GET /items/search", searchItems)
		mux.HandleFunc("GET /items/{id}", getItem)
		mux.HandleFunc("POST /items", createItem)
		mux.HandleFunc("PUT /items/{id}", updateItem)
		mux.HandleFunc("DELETE /items/{id}", deleteItem)
		mux.HandleFunc("GET /stats", stats)
		mux.HandleFunc("POST /orders", createOrder)
		mux.HandleFunc("GET /stores/{id}/sales-report", storeSalesReport)
		mux.HandleFunc("GET /reports/sales", allSalesReport)
	}

	log.Println("listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", withTiming(mux)))
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func fail(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func scanItem(row pgx.Row) (Item, error) {
	var it Item
	err := row.Scan(&it.ID, &it.Name, &it.Category, &it.PriceCents, &it.Stock)
	return it, err
}

// 1. GET /health - yalnızca uygulama: veri deposuna dokunmaz (canlılık). HTTP çerçevesinin ham maliyetini gösterir.
func health(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "UP"})
}

// 2. GET /items?after=&limit= - keyset sayfalama
func listItems(w http.ResponseWriter, r *http.Request) {
	after, _ := strconv.ParseInt(r.URL.Query().Get("after"), 10, 64)
	limit, err := strconv.Atoi(r.URL.Query().Get("limit"))
	if err != nil || limit < 1 || limit > 100 {
		limit = 50
	}
	done := track(r.Context())
	rows, err := pool.Query(r.Context(),
		"SELECT "+itemCols+" FROM items WHERE id > $1 ORDER BY id LIMIT $2", after, limit)
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer rows.Close()
	items := make([]Item, 0, limit)
	for rows.Next() {
		it, err := scanItem(rows)
		if err != nil {
			fail(w, http.StatusInternalServerError, err.Error())
			return
		}
		items = append(items, it)
	}
	done()
	writeJSON(w, http.StatusOK, items)
}

// 3. GET /items/{id}
func getItem(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		fail(w, http.StatusBadRequest, "bad id")
		return
	}
	done := track(r.Context())
	it, err := scanItem(pool.QueryRow(r.Context(), "SELECT "+itemCols+" FROM items WHERE id = $1", id))
	done()
	if errors.Is(err, pgx.ErrNoRows) {
		fail(w, http.StatusNotFound, "not found")
		return
	}
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, it)
}

// 4. POST /items
func createItem(w http.ResponseWriter, r *http.Request) {
	var in NewItem
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.Name == "" {
		fail(w, http.StatusBadRequest, "bad body")
		return
	}
	done := track(r.Context())
	it, err := scanItem(pool.QueryRow(r.Context(),
		"INSERT INTO items (name, category, price_cents, stock) VALUES ($1, $2, $3, $4) RETURNING "+itemCols,
		in.Name, in.Category, in.PriceCents, in.Stock))
	done()
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, it)
}

// 5. PUT /items/{id}
func updateItem(w http.ResponseWriter, r *http.Request) {
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
	it, err := scanItem(pool.QueryRow(r.Context(),
		"UPDATE items SET price_cents = $2, stock = $3, updated_at = now() WHERE id = $1 RETURNING "+itemCols,
		id, in.PriceCents, in.Stock))
	done()
	if errors.Is(err, pgx.ErrNoRows) {
		fail(w, http.StatusNotFound, "not found")
		return
	}
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, it)
}

// 6. DELETE /items/{id}
func deleteItem(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		fail(w, http.StatusBadRequest, "bad id")
		return
	}
	done := track(r.Context())
	tag, err := pool.Exec(r.Context(), "DELETE FROM items WHERE id = $1", id)
	done()
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	if tag.RowsAffected() == 0 {
		fail(w, http.StatusNotFound, "not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// 7. GET /items/search?q= - lower(name) önek araması (indeksli)
func searchItems(w http.ResponseWriter, r *http.Request) {
	q := strings.ToLower(r.URL.Query().Get("q"))
	if q == "" {
		fail(w, http.StatusBadRequest, "q required")
		return
	}
	done := track(r.Context())
	rows, err := pool.Query(r.Context(),
		"SELECT "+itemCols+" FROM items WHERE lower(name) LIKE $1 ORDER BY id LIMIT 20", q+"%")
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer rows.Close()
	items := make([]Item, 0, 20)
	for rows.Next() {
		it, err := scanItem(rows)
		if err != nil {
			fail(w, http.StatusInternalServerError, err.Error())
			return
		}
		items = append(items, it)
	}
	done()
	writeJSON(w, http.StatusOK, items)
}

// 8. GET /stats - tüm tabloda gruplu toplama
func stats(w http.ResponseWriter, r *http.Request) {
	done := track(r.Context())
	rows, err := pool.Query(r.Context(),
		"SELECT category, count(*)::bigint, avg(price_cents)::float8, sum(stock)::bigint FROM items GROUP BY category ORDER BY category")
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer rows.Close()
	out := make([]CategoryStat, 0, 32)
	for rows.Next() {
		var c CategoryStat
		if err := rows.Scan(&c.Category, &c.Count, &c.AvgPrice, &c.TotalStock); err != nil {
			fail(w, http.StatusInternalServerError, err.Error())
			return
		}
		out = append(out, c)
	}
	done()
	writeJSON(w, http.StatusOK, out)
}

// 9. POST /orders - tek transaction: stok düş + sipariş ekle
func createOrder(w http.ResponseWriter, r *http.Request) {
	var in NewOrder
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.Quantity < 1 {
		fail(w, http.StatusBadRequest, "bad body")
		return
	}
	ctx := r.Context()
	done := track(ctx)
	tx, err := pool.Begin(ctx)
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer tx.Rollback(ctx)

	var price int32
	err = tx.QueryRow(ctx,
		"UPDATE items SET stock = stock - $2 WHERE id = $1 AND stock >= $2 RETURNING price_cents",
		in.ItemID, in.Quantity).Scan(&price)
	if errors.Is(err, pgx.ErrNoRows) {
		fail(w, http.StatusConflict, "no stock or item")
		return
	}
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	total := int64(price) * int64(in.Quantity)
	var orderID int64
	err = tx.QueryRow(ctx,
		"INSERT INTO orders (item_id, quantity, total_cents) VALUES ($1, $2, $3) RETURNING id",
		in.ItemID, in.Quantity, total).Scan(&orderID)
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	if err := tx.Commit(ctx); err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	done()
	writeJSON(w, http.StatusCreated, map[string]int64{"order_id": orderID, "total_cents": total})
}

// 10. GET /cpu?n= - veritabanısız, saf CPU işi (n'e kadar asal sayıları say)
func cpuWork(w http.ResponseWriter, r *http.Request) {
	n, err := strconv.Atoi(r.URL.Query().Get("n"))
	if err != nil || n < 2 || n > 200000 {
		n = 50000
	}
	count := 0
	for i := 2; i <= n; i++ {
		prime := true
		for j := 2; j*j <= i; j++ {
			if i%j == 0 {
				prime = false
				break
			}
		}
		if prime {
			count++
		}
	}
	writeJSON(w, http.StatusOK, map[string]int{"n": n, "primes": count})
}

// ---- 13-14. Veritabanısız mantık uç noktaları ----

type B64Result struct {
	InputBytes   int    `json:"input_bytes"`
	EncodedBytes int    `json:"encoded_bytes"`
	Encoded      string `json:"encoded"`
}

// 13. POST /base64 - isteğin gövdesini okur ve Base64'e çevirir (veritabanı yok)
func base64Work(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 1<<20))
	if err != nil {
		fail(w, http.StatusBadRequest, "gövde okunamadı")
		return
	}
	enc := base64.StdEncoding.EncodeToString(body)
	writeJSON(w, http.StatusOK, B64Result{InputBytes: len(body), EncodedBytes: len(enc), Encoded: enc})
}

type FactResult struct {
	N             int    `json:"n"`
	Digits        int    `json:"digits"`
	FirstDigits   string `json:"first_digits"`
	TrailingZeros int    `json:"trailing_zeros"`
}

// 14. GET /factorial?n= - n! değerini büyük tamsayıyla hesaplar (veritabanı yok).
// Bilerek sıralı çarpma: Spring tarafındaki BigInteger döngüsüyle aynı algoritma (MulRange gibi ağaç çarpımı yok).
func factorial(w http.ResponseWriter, r *http.Request) {
	n, err := strconv.Atoi(r.URL.Query().Get("n"))
	if err != nil || n < 1 || n > 5000 {
		n = 1000
	}
	f := big.NewInt(1)
	m := new(big.Int)
	for i := 2; i <= n; i++ {
		f.Mul(f, m.SetInt64(int64(i)))
	}
	s := f.String()
	first := s
	if len(first) > 16 {
		first = first[:16]
	}
	writeJSON(w, http.StatusOK, FactResult{
		N: n, Digits: len(s), FirstDigits: first,
		TrailingZeros: len(s) - len(strings.TrimRight(s, "0")),
	})
}

// ---- 11-12. Satış raporları: günlük ve aylık toplamlar SQL ile değil, uygulama kodunda hesaplanır ----

type DayRow struct {
	Date    string `json:"date"`
	Orders  int64  `json:"orders"`
	Units   int64  `json:"units"`
	Revenue int64  `json:"revenue_cents"`
}

type MonthRow struct {
	Month    string   `json:"month"`
	Orders   int64    `json:"orders"`
	Units    int64    `json:"units"`
	Revenue  int64    `json:"revenue_cents"`
	AvgOrder float64  `json:"avg_order_cents"`
	Growth   *float64 `json:"growth_pct"` // bir önceki aya göre değişim; ilk ayda null
}

type StoreReport struct {
	StoreID         int32      `json:"store_id"`
	Name            string     `json:"name"`
	City            string     `json:"city"`
	TotalOrders     int64      `json:"total_orders"`
	TotalRevenue    int64      `json:"total_revenue_cents"`
	AvgDailyRevenue float64    `json:"avg_daily_revenue_cents"`
	BestDay         *DayRow    `json:"best_day"`
	Monthly         []MonthRow `json:"monthly"`
	Daily           []DayRow   `json:"daily,omitempty"`
}

type bucket struct{ orders, units, revenue int64 }

// agg, bir mağazanın satış satırlarını gün ve ay anahtarlarına göre biriktirir.
type agg struct {
	daily   map[string]*bucket
	monthly map[string]*bucket
}

func newAgg() *agg { return &agg{daily: map[string]*bucket{}, monthly: map[string]*bucket{}} }

func (a *agg) add(t time.Time, qty int32, amount int64) {
	day := t.Format("2006-01-02")
	month := day[:7]
	d := a.daily[day]
	if d == nil {
		d = &bucket{}
		a.daily[day] = d
	}
	d.orders++
	d.units += int64(qty)
	d.revenue += amount
	m := a.monthly[month]
	if m == nil {
		m = &bucket{}
		a.monthly[month] = m
	}
	m.orders++
	m.units += int64(qty)
	m.revenue += amount
}

func (a *agg) report(id int32, name, city string, withDaily bool) StoreReport {
	days := make([]string, 0, len(a.daily))
	for k := range a.daily {
		days = append(days, k)
	}
	sort.Strings(days)
	rep := StoreReport{StoreID: id, Name: name, City: city}
	var daily []DayRow
	if withDaily {
		daily = make([]DayRow, 0, len(days))
	}
	for _, k := range days {
		b := a.daily[k]
		row := DayRow{Date: k, Orders: b.orders, Units: b.units, Revenue: b.revenue}
		rep.TotalOrders += b.orders
		rep.TotalRevenue += b.revenue
		if rep.BestDay == nil || row.Revenue > rep.BestDay.Revenue {
			best := row
			rep.BestDay = &best
		}
		if withDaily {
			daily = append(daily, row)
		}
	}
	if len(days) > 0 {
		rep.AvgDailyRevenue = float64(rep.TotalRevenue) / float64(len(days))
	}
	months := make([]string, 0, len(a.monthly))
	for k := range a.monthly {
		months = append(months, k)
	}
	sort.Strings(months)
	rep.Monthly = make([]MonthRow, 0, len(months))
	var prev int64
	for i, k := range months {
		b := a.monthly[k]
		row := MonthRow{Month: k, Orders: b.orders, Units: b.units, Revenue: b.revenue}
		if b.orders > 0 {
			row.AvgOrder = float64(b.revenue) / float64(b.orders)
		}
		if i > 0 && prev > 0 {
			g := float64(b.revenue-prev) / float64(prev) * 100
			row.Growth = &g
		}
		prev = b.revenue
		rep.Monthly = append(rep.Monthly, row)
	}
	rep.Daily = daily
	return rep
}

// 11. GET /stores/{id}/sales-report - tek mağazanın günlük + aylık satış raporu.
// Satırlar önce tamamen okunur (veri süresi), toplamalar sonra UYGULAMA KODUNDA yapılır (uygulama süresi).
func storeSalesReport(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 32)
	if err != nil {
		fail(w, http.StatusBadRequest, "bad id")
		return
	}
	ctx := r.Context()
	type sale struct {
		t      time.Time
		qty    int32
		amount int64
	}
	var name, city string
	sales := make([]sale, 0, 2048)
	done := track(ctx)
	err = pool.QueryRow(ctx, "SELECT name, city FROM stores WHERE id = $1", id).Scan(&name, &city)
	if errors.Is(err, pgx.ErrNoRows) {
		done()
		fail(w, http.StatusNotFound, "not found")
		return
	}
	if err != nil {
		done()
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	rows, err := pool.Query(ctx, "SELECT sold_at, quantity, amount_cents FROM sales WHERE store_id = $1", id)
	if err != nil {
		done()
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	for rows.Next() {
		var x sale
		if err := rows.Scan(&x.t, &x.qty, &x.amount); err != nil {
			rows.Close()
			done()
			fail(w, http.StatusInternalServerError, err.Error())
			return
		}
		sales = append(sales, x)
	}
	rows.Close()
	err = rows.Err()
	done()
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	a := newAgg()
	for _, x := range sales {
		a.add(x.t, x.qty, x.amount)
	}
	writeJSON(w, http.StatusOK, a.report(int32(id), name, city, true))
}

// buildReport: gün ve ay toplamları hazırken (veri deposunda hesaplanmış) rapor alanlarını üretir: toplam, ortalama, en iyi gün, aylık büyüme.
// agg.report ile aynı sonucu verir; fark, toplamaların burada yapılmaması.
func buildReport(id int32, name, city string, days []DayRow, months []MonthRow) StoreReport {
	rep := StoreReport{StoreID: id, Name: name, City: city}
	for _, d := range days {
		rep.TotalOrders += d.Orders
		rep.TotalRevenue += d.Revenue
		if rep.BestDay == nil || d.Revenue > rep.BestDay.Revenue {
			best := d
			rep.BestDay = &best
		}
	}
	if len(days) > 0 {
		rep.AvgDailyRevenue = float64(rep.TotalRevenue) / float64(len(days))
	}
	rep.Monthly = make([]MonthRow, 0, len(months))
	var prev int64
	for i, m := range months {
		if m.Orders > 0 {
			m.AvgOrder = float64(m.Revenue) / float64(m.Orders)
		}
		if i > 0 && prev > 0 {
			g := float64(m.Revenue-prev) / float64(prev) * 100
			m.Growth = &g
		}
		prev = m.Revenue
		rep.Monthly = append(rep.Monthly, m)
	}
	return rep
}

// 12. GET /reports/sales - tüm mağazalar: günlük ve aylık toplamlar VERİTABANINDA (SQL GROUP BY) hesaplanır;
// uygulama yalnızca hazır toplamları rapora dizer (en iyi gün, büyüme yüzdesi).
func allSalesReport(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	type store struct {
		id         int32
		name, city string
	}
	var stores []store
	days := map[int32][]DayRow{}
	months := map[int32][]MonthRow{}
	done := track(ctx)
	srows, err := pool.Query(ctx, "SELECT id, name, city FROM stores ORDER BY id")
	if err != nil {
		done()
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	for srows.Next() {
		var st store
		if err := srows.Scan(&st.id, &st.name, &st.city); err != nil {
			srows.Close()
			done()
			fail(w, http.StatusInternalServerError, err.Error())
			return
		}
		stores = append(stores, st)
	}
	srows.Close()

	drows, err := pool.Query(ctx, "SELECT store_id, to_char(sold_at, 'YYYY-MM-DD'), count(*)::bigint, sum(quantity)::bigint, sum(amount_cents)::bigint "+
		"FROM sales GROUP BY store_id, 2 ORDER BY store_id, 2")
	if err != nil {
		done()
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	for drows.Next() {
		var sid int32
		var d DayRow
		if err := drows.Scan(&sid, &d.Date, &d.Orders, &d.Units, &d.Revenue); err != nil {
			drows.Close()
			done()
			fail(w, http.StatusInternalServerError, err.Error())
			return
		}
		days[sid] = append(days[sid], d)
	}
	drows.Close()

	mrows, err := pool.Query(ctx, "SELECT store_id, to_char(sold_at, 'YYYY-MM'), count(*)::bigint, sum(quantity)::bigint, sum(amount_cents)::bigint "+
		"FROM sales GROUP BY store_id, 2 ORDER BY store_id, 2")
	if err != nil {
		done()
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	for mrows.Next() {
		var sid int32
		var m MonthRow
		if err := mrows.Scan(&sid, &m.Month, &m.Orders, &m.Units, &m.Revenue); err != nil {
			mrows.Close()
			done()
			fail(w, http.StatusInternalServerError, err.Error())
			return
		}
		months[sid] = append(months[sid], m)
	}
	mrows.Close()
	done()

	out := make([]StoreReport, 0, len(stores))
	for _, st := range stores {
		out = append(out, buildReport(st.id, st.name, st.city, days[st.id], months[st.id]))
	}
	writeJSON(w, http.StatusOK, out)
}
