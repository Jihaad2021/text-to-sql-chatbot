# Panduan Sistem Chatbot BI — Mapping Pertanyaan ke Data & Metodologi

> **Tujuan dokumen ini:** Menjadi referensi bagi sistem chatbot untuk memahami data apa yang tersedia, bagaimana mengaksesnya, dan bagaimana "berpikir" saat menjawab setiap pertanyaan analitis.
>
> **Prinsip utama:** Chatbot TIDAK boleh menjawab dengan generalisasi. Setiap jawaban harus menyebut angka spesifik dari data yang direferensikan. Jika data tidak tersedia, katakan "data tidak tersedia untuk periode ini" — jangan mengarang.

---

## BAGIAN 1 — INVENTARIS DATA YANG TERSEDIA

### 1.1 Metrics Dict (Tersedia di semua jawaban)

Semua field di bawah ini tersedia dalam objek `metrics` yang di-load dari `outputs/data_cache/metrics_*.json`.

#### KPI Utama
| Field | Tipe | Isi |
|---|---|---|
| `total_vol` | int | Total transaksi periode ini |
| `total_rev` | float | Total revenue periode ini (Rp) |
| `avg_sr` | float | Average Success Rate (%) |
| `total_users` | int | Unique user aktif |
| `arpu_val` | float | ARPU periode ini |
| `vol_wow` | float | % perubahan volume vs periode lalu (MoM) |
| `rev_wow` | float | % perubahan revenue vs periode lalu |
| `sr_wow` | float | Perubahan SR (dalam pp) |
| `total_users_wow` | float | % perubahan users |
| `arpu_wow` | float | % perubahan ARPU |
| `daily_avg_trx` | float | Rata-rata transaksi per hari |
| `duration` | int | Jumlah hari dalam periode |
| `date_range_str` | str | Rentang tanggal periode |

#### Chart / Time Series
| Field | Tipe | Isi |
|---|---|---|
| `chart_days` | list[str] | Label hari ("Mon 01/06") |
| `chart_daily_vol` | list[int] | Volume harian (ribuan) |
| `chart_daily_rev` | list[float] | Revenue harian (miliar Rp) |
| `chart_daily_sr` | list[float] | SR harian (%) |
| `chart_daily_arpu` | list[float] | ARPU harian |
| `chart_prev_daily_vol` | list[int] | Volume harian periode sebelumnya |
| `prev_avg_vol` | int | Rata-rata volume harian periode lalu |
| `hourly_averages` | list[float] | Rata-rata volume per jam (24 elemen, indeks 0=00.00) |
| `avg_weekday_vol` | int | Rata-rata volume pada hari kerja |
| `avg_weekend_vol` | int | Rata-rata volume pada hari weekend |

#### Proyeksi
| Field | Akses | Isi |
|---|---|---|
| `projection.available` | bool | true = periode belum selesai |
| `projection.m1_trx` | int | Proyeksi volume akhir bulan (metode pace) |
| `projection.m1_rev` | int | Proyeksi revenue akhir bulan |
| `projection.m2_trx` | int | Proyeksi alternatif (historical avg) |
| `projection.confidence` | str | "tinggi" / "sedang" / "rendah" |
| `projection.scenarios.optimis` | dict | Skenario terbaik (vol, rev, sr, uu) |
| `projection.scenarios.sedang` | dict | Skenario tengah |
| `projection.scenarios.pesimis` | dict | Skenario terburuk |

---

### 1.2 Tabel per Entitas

#### Partner Table — `metrics["partner_table"]`
Setiap elemen adalah dict satu partner:
```
name              → nama partner (telkomsel, gopay, dana, ...)
total_trx         → volume transaksi (int)
total_revenue     → revenue (int, Rp)
share             → % kontribusi terhadap total volume
sr                → success rate (float, %)
sr_delta          → perubahan SR vs periode lalu (pp)
arpu              → ARPU (float, ribu Rp)
mom_trx_growth    → % MoM perubahan volume
mom_rev_growth    → % MoM perubahan revenue
status            → "Normal" / "Watch" / "ALERT"
unique_users      → jumlah unique user
avg_trx_value     → rata-rata nilai per transaksi (Rp)
```

#### Product Table — `metrics["product_table"]`
```
name              → nama produk
total_trx         → volume transaksi
total_revenue     → revenue (Rp)
sr                → success rate (%)
wow               → % perubahan vs periode lalu (MoM)
unknown-product   → bool, true jika produk tidak dikenali
```
Subset khusus:
- `metrics["product_gainers"]` → 5 produk dengan wow tertinggi
- `metrics["product_losers"]` → 5 produk dengan wow terendah

#### Channel Table — `metrics["channel_table"]`
```
name              → kode channel (i1, f0, b0, ig, ...)
total_trx         → volume transaksi
total_revenue     → revenue (Rp)
share             → % kontribusi terhadap total
sr                → success rate (%)
mom_trx_growth    → % MoM perubahan volume
```
Mapping kode channel:
- `i1` = MyTelkomsel App
- `f0, f4, f5` = UMB (Unstructured)
- `b0, b3, a0` = WEC (Web/API)
- `ig` = MyTelkomsel Basic

---

### 1.3 Alert Structures

#### Trend Alerts — `metrics["alerts"][segment]`
Segment: `"transaction"`, `"product"`, `"partner"`, `"channel"`

```
level             → "red" / "amber" / "green" (status keseluruhan segment)
streak            → berapa hari berturut-turut tren turun
period_decline    → % perubahan dari hari pertama ke terakhir
down_pct          → % hari-hari yang mencatat penurunan dalam periode
mom_vol           → % MoM perubahan volume
mom_rev           → % MoM perubahan revenue
message           → narasi ringkas status
card_summary      → satu kalimat untuk tampilan card
flagged           → list entitas yang bermasalah (lihat sub-struktur per segment)
period_highlights → list periode anomali (lonjakan/penurunan signifikan)
metrics           → breakdown per dimensi: volume, revenue, sr, mom
```

Untuk `flagged` di partner:
```
partner           → nama partner
level             → "red" / "amber"
streak            → consecutive decline days
mom_pct           → % MoM change volume
rev_level         → level alert revenue
rev_mom_pct       → % MoM change revenue
```

#### DoD Alerts — `metrics["dod_alerts"]`
List alert harian (hari terakhir vs hari sebelumnya):
```
entity_name       → nama entitas (e.g. "Daily Transactions", "Telkomsel", "Paket Internet")
entity_type       → "total" / "partner" / "product" / "channel" / "category"
direction         → "spike" (lonjakan) / "drop" (penurunan)
actual_value      → % perubahan aktual
level             → WARNING / CRITICAL / INFO
today_value       → nilai absolut hari ini
yesterday_value   → nilai absolut kemarin
streak_days       → berapa hari berturut-turut dalam arah yang sama
```

---

### 1.4 AI Insights (Tersimpan di Cache LLM)

Field-field ini tersedia jika pipeline LLM sudah dijalankan:

```
metrics["ai_insights"]["transaction"]["ai_insight"]       → narasi executive transaksi
metrics["ai_insights"]["transaction"]["root_cause_analysis"] → analisis akar masalah
metrics["ai_insights"]["transaction"]["recommendation"]   → rekomendasi strategis
metrics["ai_insights"]["transaction"]["qa"]               → list Q&A (5 pasang)

metrics["ai_insights"]["product"]["ai_insight"]           → narasi executive produk
metrics["ai_insights"]["partner"]["ai_insight"]           → narasi executive partner
metrics["ai_insights"]["channel"]["ai_insight"]           → narasi executive channel
```

Untuk analisis periode berlapis (3 layer):
```
metrics["transaction_period"]["hari_ini"]["q1_interp"]    → interpretasi AI hari ini vs kemarin
metrics["transaction_period"]["hari_ini"]["q2_interp"]    → interpretasi distribusi jam
metrics["transaction_period"]["hari_ini"]["three_day"]["q_interp"] → interpretasi tren 3 hari
metrics["transaction_period"]["hari_ini"]["mom"]["..."]   → perbandingan MoM tanggal sama
metrics["transaction_period"]["mingguan"]["q1_interp"]    → interpretasi tren mingguan
```

---

## BAGIAN 2 — METODOLOGI BERPIKIR

### Prinsip Umum

Sebelum menjawab pertanyaan apapun, lakukan 4 langkah:

```
1. IDENTIFIKASI  → Pertanyaan ini tentang dimensi apa? (volume / revenue / SR / growth / konsentrasi / risk)
2. AMBIL DATA    → Field mana di atas yang relevan?
3. HITUNG SINYAL → Angka apa yang perlu dihitung dari raw data?
4. BERI VERDICT  → Sehat / Perhatian / Kritis — dengan threshold yang jelas
```

### Threshold Standar (Gunakan ini untuk scoring)

| Metrik | Sehat (Hijau) | Perhatian (Kuning) | Kritis (Merah) |
|---|---|---|---|
| MoM Volume Growth | > 0% | -10% s/d 0% | < -10% |
| Success Rate | > 98% | 95%–98% | < 95% |
| Konsentrasi Top-2 | < 50% | 50%–70% | > 70% |
| Streak Turun (hari) | 0–1 | 2–3 | ≥ 4 |
| Partner Turun (%) | < 30% dari total | 30%–50% | > 50% |
| DoD Spike/Drop | < ±20% | ±20%–40% | > ±40% |

### Formula Standar

```python
# Konsentrasi (share akumulatif top-N)
top2_share = sum([p["share"] for p in partner_table[:2]])

# Distribusi pertumbuhan
growing = len([p for p in partner_table if p["mom_trx_growth"] > 0])
declining = len([p for p in partner_table if p["mom_trx_growth"] < 0])
stable = len(partner_table) - growing - declining

# ARPT (Avg Revenue per Transaction)
arpt = total_revenue / total_trx  # Rp per transaksi

# Momentum (apakah tren mengakselerasi atau melambat)
recent_half = avg(chart_daily_vol[-7:])
early_half = avg(chart_daily_vol[:7])
momentum = (recent_half - early_half) / early_half * 100  # % change

# Anomaly detection (hari yang menyimpang > 2x std dev)
mean_vol = avg(chart_daily_vol)
std_vol = stdev(chart_daily_vol)
anomaly_days = [i for i, v in enumerate(chart_daily_vol) if abs(v - mean_vol) > 2 * std_vol]
```

---

## BAGIAN 3 — MAPPING PERTANYAAN KE DATA & PENDEKATAN

> Format tiap entri:
> - **Data yang diakses** → field spesifik
> - **Kalkulasi yang diperlukan** → formula atau logika
> - **Pola jawaban** → struktur narasi

---

### SEGMENT 1 — TRANSACTIONS

---

#### Q1. Bagaimana performa volume transaksi periode ini?

**Data:**
- `total_vol`, `vol_wow`, `prev_vol`, `daily_avg_trx`, `duration`

**Kalkulasi:**
- Hitung rata-rata per hari = `total_vol / duration`
- Bandingkan `vol_wow` terhadap threshold: > 0% → naik, -10%–0% → flat, < -10% → turun

**Pola jawaban:**
```
Volume [naik/turun/flat] [X]% MoM — total [total_vol] transaksi dalam [duration] hari
(rata-rata [daily_avg_trx]/hari). [Konteks: periode lalu [prev_vol], selisih [total_vol - prev_vol].)
```

---

#### Q2. Bagaimana performa pendapatan periode ini?

**Data:**
- `total_rev`, `rev_wow`, `prev_rev`, `arpu_val`, `arpu_wow`

**Kalkulasi:**
- Revenue per hari = `total_rev / duration`
- Cek apakah ARPU naik/turun searah dengan revenue

**Pola jawaban:**
```
Revenue [naik/turun] [X]% MoM — total [total_rev]. ARPU [arpu_val], [naik/turun] [arpu_wow]%
dari periode lalu. [Jika ARPU naik tapi volume turun → efisiensi naik, volume turun.]
```

---

#### Q3. Seberapa andal platform secara teknis (Success Rate)?

**Data:**
- `avg_sr`, `sr_wow`, `chart_daily_sr`, `alerts["transaction"]["metrics"]["sr"]`

**Kalkulasi:**
- `min_sr = min(chart_daily_sr)` → hari terburuk
- `max_sr = max(chart_daily_sr)` → hari terbaik
- `sr_range = max_sr - min_sr` → stabilitas SR
- Cek apakah ada hari dengan `sr < 95%` (threshold kritis)

**Pola jawaban:**
```
SR rata-rata [avg_sr]%, [naik/turun] [sr_wow] pp dari periode lalu.
SR terendah [min_sr]% pada hari [tanggal]. [Range [sr_range] pp — platform [stabil/fluktuatif].]
[Jika ada hari < 95%: PERHATIAN — ada [n] hari dengan SR di bawah threshold.]
```

---

#### Q4. Bagaimana tren pengguna aktif?

**Data:**
- `total_users`, `total_users_wow`, `prev_total_users`

**Kalkulasi:**
- Selisih user = `total_users - prev_total_users`
- Arah tren: naik / turun / flat

**Pola jawaban:**
```
User aktif [total_users] ([naik/turun] [total_users_wow]% dari [prev_total_users]).
[Konteks: jika user naik tapi revenue turun → transaksi kecil-kecil; jika sebaliknya → konsentrasi user high-value.]
```

---

#### Q5. Apakah nilai belanja per pengguna (ARPU) berubah?

**Data:**
- `arpu_val`, `arpu_wow`, `prev_arpu_val`

**Kalkulasi:**
- Selisih absolut = `arpu_val - prev_arpu_val` (Rp)
- Cek konsistensi: apakah ARPU searah dengan revenue?

**Pola jawaban:**
```
ARPU [arpu_val] ([naik/turun] [arpu_wow]% dari [prev_arpu_val]).
[Jika naik: user lebih banyak belanja per sesi / produk bernilai lebih tinggi terjual.]
[Jika turun: proporsi transaksi kecil lebih besar, atau user baru yang belum loyal.]
```

---

#### Q6. Bagaimana performa hari terakhir dibanding hari sebelumnya?

**Data:**
- `dod_alerts` — filter `entity_type == "total"`
- `chart_daily_vol[-1]` vs `chart_daily_vol[-2]`
- `chart_daily_rev[-1]` vs `chart_daily_rev[-2]`
- `transaction_period.hari_ini.q1_text` + `q1_interp` (jika tersedia)

**Kalkulasi:**
- `vol_dod = (chart_daily_vol[-1] - chart_daily_vol[-2]) / chart_daily_vol[-2] * 100`
- `rev_dod = (chart_daily_rev[-1] - chart_daily_rev[-2]) / chart_daily_rev[-2] * 100`
- Cek DoD alerts untuk entity_name "Daily Transactions" dan "Daily Revenue"

**Pola jawaban:**
```
[Tanggal hari terakhir]: [vol hari ini] transaksi ([±X]% vs kemarin [vol kemarin]).
Revenue [rev hari ini] ([±Y]%). [Jika ada dod_alerts CRITICAL: ⚠️ perlu perhatian.]
[transaction_period.hari_ini.q1_interp jika tersedia]
```

---

#### Q7. Bagaimana performa hari ini dibanding tanggal yang sama bulan lalu?

**Data:**
- `transaction_period.hari_ini.mom` (jika tersedia)
- Field: `vol_chg`, `rev_chg`, `last_day`, `mom_day`

**Pola jawaban:**
```
Tanggal [last_day] vs [mom_day] (MoM same-date):
Volume [±vol_chg]%, Revenue [±rev_chg]%.
[Jika tidak tersedia: data MoM same-date tidak tersedia untuk periode ini.]
```

---

#### Q8. Bagaimana arah tren dalam 3 hari terakhir?

**Data:**
- `transaction_period.hari_ini.three_day` (jika `n >= 3`)
- Field: `trend_class`, `trend_label`, `vc01`, `vc12`, `q_interp`
- Fallback: `chart_daily_vol[-3:]`

**Kalkulasi:**
- Jika `three_day` tidak tersedia: hitung sendiri `vol[-3], vol[-2], vol[-1]`
- Tentukan arah: accelerating_decline / decelerating_decline / recovery / accelerating_growth / stable

**Pola jawaban:**
```
3 hari terakhir: [hari-3] → [hari-2] → [hari-1].
Tren: [trend_label]. [q_interp jika tersedia]
Perubahan: H-2→H-1: [vc01]%, H-1→Hari ini: [vc12]%.
```

---

#### Q9. Bagaimana distribusi transaksi sepanjang hari?

**Data:**
- `hourly_averages` (24 elemen, 0=jam 00.00)
- `avg_weekday_vol`, `avg_weekend_vol`
- `transaction_period.hari_ini.q2_text` + `q2_interp`

**Kalkulasi:**
- `peak_hour = argmax(hourly_averages)`
- `peak_pct = hourly_averages[peak_hour] / sum(hourly_averages) * 100`
- Tentukan apakah pola bimodal (2 puncak) atau unimodal

**Pola jawaban:**
```
Puncak aktivitas jam [peak_hour]:00 ([peak_pct]% transaksi harian).
Weekday avg [avg_weekday_vol], Weekend avg [avg_weekend_vol] ([perbedaan]%).
[q2_interp jika tersedia]
```

---

#### Q10. Bagaimana tren volume berubah dari minggu ke minggu?

**Data:**
- `transaction_period.mingguan.weeks` — list per minggu
- Field per minggu: `label`, `date_start`, `date_end`, `vol_avg`, `sr`, `vol_wow`
- `transaction_period.mingguan.overall_chg`, `q1_text`, `q1_interp`

**Kalkulasi:**
- Cek `vol_wow` tiap minggu: berapa minggu positif vs negatif?
- `overall_chg` = perubahan dari minggu 1 ke minggu terakhir

**Pola jawaban:**
```
[nw] minggu dianalisis. Perubahan keseluruhan: [overall_chg]%.
- Minggu 1 ([dates]): [vol_avg]/hari
- Minggu 2 ([dates]): [vol_avg]/hari ([±wow]%)
- ...
[Jika turun konsisten: pola declining trend. Jika mixed: fluktuatif.]
[q1_interp jika tersedia]
```

---

#### Q11. Bagaimana bentuk tren keseluruhan selama periode ini?

**Data:**
- `chart_daily_vol` (seluruh series)
- `alerts["transaction"]["period_decline"]`
- `alerts["transaction"]["down_pct"]`
- `alerts["transaction"]["streak"]`

**Kalkulasi:**
- Hitung `momentum`: `avg(vol[-7:])` vs `avg(vol[:7])`
- Hitung variasi: `stdev(chart_daily_vol) / avg(chart_daily_vol) * 100` (coefficient of variation)
- Klasifikasi pola: U-shape / inverted-U / declining / ascending / flat/volatile

**Pola jawaban:**
```
Selama [duration] hari: [period_decline]% perubahan keseluruhan.
[down_pct]% hari mencatat penurunan. Streak turun terpanjang: [streak] hari.
Momentum: [7 hari terakhir] vs [7 hari pertama] = [±X]%.
Pola umum: [U-shape / declining / ascending / volatile].
```

---

#### Q12. Adakah hari-hari anomali yang menyimpang jauh dari rata-rata?

**Data:**
- `chart_daily_vol`, `chart_days`
- `alerts["transaction"]["period_highlights"]`

**Kalkulasi:**
- `mean = avg(chart_daily_vol)`
- `std = stdev(chart_daily_vol)`
- Anomali = hari dengan `|vol - mean| > 2 * std`
- Cek `period_highlights` untuk event anomali yang sudah terdeteksi sistem

**Pola jawaban:**
```
Rata-rata harian: [mean] transaksi.
Anomali terdeteksi:
- [Tanggal]: [vol] transaksi ([±X]% dari rata-rata) — [konteks dari period_highlights]
[Jika tidak ada anomali: Volume relatif stabil sepanjang periode.]
```

---

#### Q13. Apakah volume, pendapatan, dan SR bergerak seirama?

**Data:**
- `chart_daily_vol`, `chart_daily_rev`, `chart_daily_sr`
- `vol_wow`, `rev_wow`, `sr_wow`

**Kalkulasi:**
- Cek arah ketiga metrik: searah (semua naik/turun) atau divergen
- Jika volume naik tapi SR turun: masalah teknis saat volume tinggi
- Jika revenue naik tapi volume turun: ARPU naik (mix shift ke produk mahal)

**Pola jawaban:**
```
Volume [±vol_wow]%, Revenue [±rev_wow]%, SR [±sr_wow] pp.
[Searah/Divergen]:
- Jika divergen: [interpretasi spesifik penyebab divergensi]
[Korelasi: ketiga metrik bergerak seirama = sistem sehat; divergensi = sinyal investigasi.]
```

---

### SEGMENT 2 — PRODUCTS

---

#### Q14. Bagaimana kondisi kesehatan portfolio produk secara keseluruhan?

**Data:**
- `product_table` (seluruh list)
- `alerts["product"]["level"]`, `alerts["product"]["flagged"]`
- `ai_insights.product.ai_insight` (jika tersedia)

**Kalkulasi:**
- `total_products = len(product_table)`
- `growing = len([p for p in product_table if p["wow"] > 0])`
- `declining = len([p for p in product_table if p["wow"] < 0])`
- `sr_below_95 = [p["name"] for p in product_table if p["sr"] < 95]`
- `top5_share = sum([p["total_trx"] for p in product_table[:5]]) / total_vol * 100`

**Verdict scoring:**
- Hijau: > 60% produk tumbuh AND tidak ada SR < 95%
- Kuning: 40–60% tumbuh ATAU ada 1–2 produk SR < 95%
- Merah: < 40% tumbuh ATAU ada > 2 produk SR < 95%

**Pola jawaban:**
```
Portfolio [n] produk aktif: [growing] tumbuh, [declining] turun, [stable] flat.
Konsentrasi: Top-5 menguasai [top5_share]% volume.
SR: [Jika sr_below_95 kosong: semua produk di atas threshold] / [Jika ada: [produk X] SR [Y]%]
Verdict keseluruhan: [SEHAT / PERHATIAN / KRITIS] — [1 kalimat alasan]
```

---

#### Q15. Bagaimana struktur konsentrasi revenue — apakah ada risiko ketergantungan?

**Data:**
- `product_table` (sorted by revenue descending)
- Gunakan field `total_revenue` tiap produk

**Kalkulasi:**
- `top1_rev_share = product_table[0]["total_revenue"] / sum([p["total_revenue"] for p in product_table]) * 100`
- `top3_rev_share` = akumulasi top-3
- `top5_rev_share` = akumulasi top-5
- HHI approximation: `sum([(p["total_revenue"]/total_rev*100)**2 for p in product_table])`

**Threshold:**
- Top-3 share < 50% = Terdiversifikasi
- Top-3 share 50–70% = Konsentrasi moderat
- Top-3 share > 70% = Ketergantungan tinggi

**Pola jawaban:**
```
Top-1 produk: [nama] ([top1_rev_share]% revenue).
Top-3 akumulasi: [top3_rev_share]%.
Risiko konsentrasi: [Rendah / Moderat / Tinggi].
[Jika tinggi: Ketergantungan pada [produk X] berarti jika produk ini turun, revenue total terdampak signifikan.]
```

---

#### Q16. Produk mana yang mencatat momentum pertumbuhan terkuat?

**Data:**
- `product_gainers` (top 5 produk dengan wow tertinggi)
- Field: `name`, `wow`, `total_trx`, `total_revenue`

**Pola jawaban:**
```
Top pertumbuhan periode ini:
1. [produk]: +[wow]% MoM — [total_trx] trx, revenue [total_revenue]
2. [produk]: +[wow]% MoM — ...
...
[Konteks: produk yang baru masuk atau recovery dari penurunan bulan lalu?]
```

---

#### Q17. Produk mana yang mengalami tekanan dan seberapa signifikan dampaknya?

**Data:**
- `product_losers` (top 5 produk dengan wow terendah)
- `alerts["product"]["flagged"]` (produk dengan streak turun)
- Field: `name`, `wow`, `total_trx`, `total_revenue`, `sr`

**Kalkulasi:**
- Revenue impact = `|wow| * total_revenue / 100` (estimasi revenue yang hilang)

**Pola jawaban:**
```
Produk dalam tekanan:
1. [produk]: [wow]% MoM, volume [total_trx], estimasi revenue hilang ~[X]
2. [produk]: ...
[Produk dengan streak turun dari alerts: [nama] sudah [streak] hari berturut-turut.]
[SR: jika ada yang < 95%, tambahkan konteks masalah teknis.]
```

---

#### Q18. Bagaimana dua segmen nilai produk berbeda?

**Data:**
- `product_table` — pisahkan berdasarkan avg_trx_value atau nama produk
- Identifikasi segmen: produk premium (harga tinggi, volume rendah) vs produk massal (harga rendah, volume tinggi)

**Kalkulasi:**
- Hitung `avg_trx_value` per produk jika tersedia
- Atau gunakan `total_revenue / total_trx` per produk
- Sortir dan identifikasi dua cluster

**Pola jawaban:**
```
Segmen massal (transaksi tinggi, nilai rendah): [list produk], avg [X] Rp/trx
Segmen premium (transaksi rendah, nilai tinggi): [list produk], avg [Y] Rp/trx
[Implikasi: segmen premium berkontribusi [Z]% revenue dari [W]% volume.]
```

---

#### Q19. Produk Top 10 mana yang paling bergerak hari ini dibanding kemarin?

**Data:**
- `dod_alerts` — filter `entity_type == "product"`
- Field: `entity_name`, `direction`, `actual_value`, `today_value`, `yesterday_value`, `level`

**Pola jawaban:**
```
Pergerakan produk hari ini (DoD):
Lonjakan (Spike):
- [produk]: +[actual_value]% ([yesterday_value] → [today_value] trx) [level badge]

Penurunan (Drop):
- [produk]: [actual_value]% ([yesterday_value] → [today_value] trx) [level badge]

[Jika tidak ada dod_alerts produk: tidak ada pergerakan signifikan hari ini.]
```

---

#### Q20. Bagaimana volume dan SR produk Unknown hari ini dibanding kemarin?

**Data:**
- `dod_alerts` — filter `entity_name` yang mengandung "Unknown"
- `product_table` — filter `unknown-product == true`

**Pola jawaban:**
```
Produk Unknown: [total_trx] trx hari ini ([±X]% vs kemarin).
SR: [sr]%. [Jika SR < 95%: ⚠️ SR produk Unknown di bawah threshold.]
[Jika tidak ada data DoD: tidak ada perubahan signifikan pada produk Unknown hari ini.]
```

---

#### Q21. Produk mana yang mencatat SR di bawah 95% hari ini?

**Data:**
- `dod_alerts` — filter tipe SR (entity_type yang terkait SR, jika ada)
- `product_table` — filter `sr < 95`

**Kalkulasi:**
- `low_sr_products = [p for p in product_table if p["sr"] < 95]`

**Pola jawaban:**
```
[Jika ada]: Produk dengan SR < 95%:
- [produk]: SR [sr]%, volume [total_trx] trx

[Jika tidak ada]: Semua produk mencatat SR ≥ 95% pada periode ini.
```

---

#### Q22. Produk mana yang aktif kemarin tapi tidak ada transaksi hari ini?

**Data:**
- `dod_alerts` — filter `direction == "drop"` dengan `today_value == 0` atau mendekati nol
- `transaction_period.hari_ini` jika tersedia

**Pola jawaban:**
```
[Jika terdeteksi]: Produk aktif kemarin, nihil hari ini:
- [produk]: [yesterday_value] trx kemarin → 0 hari ini
[Jika tidak ada]: Semua produk aktif kemarin masih aktif hari ini.
```

---

#### Q23. Produk mana yang paling banyak bergerak dari sisi revenue hari ini?

**Data:**
- `dod_alerts` — filter `entity_type == "product"`, gunakan `rev_dod_pct`, `rev_today_value`, `rev_yesterday_value`

**Pola jawaban:**
```
Pergerakan revenue produk hari ini:
Kenaikan terbesar: [produk] +[rev_dod_pct]% (Rp [rev_yesterday_value] → Rp [rev_today_value])
Penurunan terbesar: [produk] [rev_dod_pct]% (...)
```

---

#### Q24. Produk Top 10 yang konsisten tumbuh atau turun minggu ke minggu?

**Data:**
- `transaction_period.mingguan.weeks` — analisis per produk jika tersedia
- `alerts["product"]["period_highlights"]` → streak naik/turun

**Catatan:** Jika data mingguan per produk tidak tersedia, gunakan `product_table.wow` sebagai proxy untuk trend keseluruhan.

**Pola jawaban:**
```
Konsisten tumbuh [n] minggu: [produk-produk]
Konsisten turun [n] minggu: [produk-produk]
[Jika data tidak tersedia per minggu: gunakan MoM sebagai indikator direction.]
```

---

#### Q25 – Q28. Pertanyaan mingguan produk lainnya

Gunakan pendekatan sama dengan Q24. Akses `transaction_period.mingguan` + `alerts["product"]`. Untuk pertanyaan konsentrasi mingguan (Q27), hitung `top5_share` dari `product_table` dan gunakan `period_highlights` untuk mendeteksi pergeseran.

---

#### Q29. Produk Top 10 momentum terkuat/terlemah sepanjang periode?

**Data:**
- `product_gainers` (terkuat)
- `product_losers` (terlemah)
- `alerts["product"]["history_movers"]`

**Pola jawaban:**
```
Momentum terkuat: [product_gainers top 3 dengan wow + total_trx]
Momentum terlemah: [product_losers top 3 dengan wow + total_trx]
[history_movers: produk dengan event signifikan — flash sale atau trend shift jangka panjang]
```

---

#### Q30 – Q33. Analisis periode produk

Gunakan kombinasi `product_table`, `alerts["product"]`, dan `ai_insights.product` untuk menjawab pertanyaan tentang Unknown, distribusi pertumbuhan, konsentrasi revenue, dan SR threshold sepanjang periode.

---

### SEGMENT 3 — PARTNERS

---

#### Q34. Bagaimana kondisi kesehatan ekosistem partner secara keseluruhan?

**Data:**
- `partner_table` (seluruh list)
- `alerts["partner"]["level"]`
- `alerts["partner"]["metrics"]`
- `ai_insights.partner.ai_insight`

**Kalkulasi — 5 dimensi:**
```
1. Volume health:
   mom_overall = avg([p["mom_trx_growth"] for p in partner_table])
   → Hijau: > 0% | Kuning: -10–0% | Merah: < -10%

2. Revenue concentration:
   top2_rev_share = sum([p["total_revenue"] for p in partner_table[:2]]) / total_rev * 100
   → Hijau: < 50% | Kuning: 50–70% | Merah: > 70%

3. SR health:
   sr_below_95 = [p for p in partner_table if p["sr"] < 95]
   → Hijau: 0 partner | Kuning: 1 partner | Merah: ≥ 2 partner

4. Growth distribution:
   growing_count = len([p for p in partner_table if p["mom_trx_growth"] > 0])
   growth_ratio = growing_count / len(partner_table)
   → Hijau: > 60% | Kuning: 40–60% | Merah: < 40%

5. Stability:
   max_streak = alerts["partner"]["streak"]
   → Hijau: ≤ 1 | Kuning: 2–3 | Merah: ≥ 4
```

**Verdict:** Mayoritas dari 5 dimensi menentukan overall verdict.

**Pola jawaban:**
```
Ekosistem [n] partner aktif — Verdict: [SEHAT / PERHATIAN / KRITIS]

Dimensi:
- Volume: [verdict] — [growing_count]/[n] partner tumbuh, avg MoM [X]%
- Konsentrasi: [verdict] — Top-2 menguasai [top2_rev_share]% revenue
- SR: [verdict] — [Semua ≥ 95% / Partner [X] SR [Y]%]
- Stabilitas: [verdict] — streak turun terpanjang [max_streak] hari

[ai_insights jika tersedia]
```

---

#### Q35. Seberapa besar risiko konsentrasi — siapa yang mendominasi?

**Data:**
- `partner_table` — field `name`, `share`, `total_revenue`, `mom_trx_growth`

**Kalkulasi:**
- Urutkan berdasarkan `total_revenue` descending
- Hitung kumulatif share revenue top-1, top-2, top-3
- Bandingkan dengan threshold (lihat BAGIAN 2)

**Pola jawaban:**
```
Distribusi revenue:
- [Partner #1]: [share_rev]% revenue, [share_vol]% volume
- [Partner #2]: [share_rev]% revenue, [share_vol]% volume
- Top-2 akumulasi: [X]% revenue

Risiko: [Rendah/Moderat/Tinggi]
[Jika tinggi: Ketergantungan pada [partner] berarti jika partner ini bermasalah, revenue total turun ~[X]%]
```

---

#### Q36. Partner mana yang menunjukkan momentum pertumbuhan terkuat?

**Data:**
- `partner_table` — sortir `mom_trx_growth` descending
- `alerts["partner"]["flagged"]` untuk validasi level

**Pola jawaban:**
```
Momentum terkuat:
1. [partner]: +[mom_trx_growth]% MoM — [total_trx] trx, revenue [total_revenue]
2. [partner]: +[mom_trx_growth]% MoM — ...
```

---

#### Q37. Partner mana yang menunjukkan tanda risiko atau penurunan performa?

**Data:**
- `alerts["partner"]["flagged"]` (partner dengan level red/amber)
- Field: `partner`, `level`, `streak`, `mom_pct`, `rev_level`, `rev_mom_pct`
- `partner_table` — filter `status == "Watch"` atau `status == "ALERT"`

**Pola jawaban:**
```
Partner berisiko:
[KRITIS] [partner]: [mom_pct]% MoM, streak [streak] hari turun berturut-turut
[PERHATIAN] [partner]: [mom_pct]% MoM, revenue [rev_mom_pct]%
[Jika tidak ada: Tidak ada partner dalam status risiko saat ini.]
```

---

#### Q38. Bagaimana efisiensi revenue per partner — siapa yang paling bernilai?

**Data:**
- `partner_table` — field `name`, `total_revenue`, `total_trx`, `arpu`, `avg_trx_value`

**Kalkulasi:**
- `revenue_per_trx = total_revenue / total_trx` (ARPT per partner)
- `arpu` sudah tersedia langsung
- Identifikasi partner "high-value": ARPU tinggi + volume moderat

**Pola jawaban:**
```
Efisiensi revenue per partner:
- Tertinggi ARPU: [partner] — [arpu] Rp/user
- ARPT tertinggi: [partner] — [revenue_per_trx] Rp/trx
[Partner yang value-driven vs volume-driven: ...]
```

---

#### Q39 – Q41. Analisis Harian Partner

Gunakan `dod_alerts` filter `entity_type == "partner"`:
- **Q39** (volume): `direction == "spike"/"drop"`, sort by `|actual_value|`
- **Q40** (revenue): gunakan `rev_dod_pct`, `rev_today_value`, `rev_yesterday_value`
- **Q41** (nihil hari ini): filter `direction == "drop"` dengan `today_value` mendekati 0

---

#### Q42 – Q45. Analisis Mingguan Partner

Gunakan `alerts["partner"]["period_highlights"]` dan `transaction_period.mingguan` untuk konteks minggu per minggu. Untuk Q43 (SR), gunakan `partner_table.sr` + `partner_table.sr_delta`. Untuk Q44–Q45, hitung konsentrasi dan pergeseran posisi dari `partner_table.share`.

---

#### Q46 – Q49. Analisis Periode Partner

- **Q46 (momentum):** Gunakan `partner_table.mom_trx_growth`, `alerts["partner"]["history_movers"]`
- **Q47 (distribusi):** Hitung `growing/stable/declining` dari `mom_trx_growth`
- **Q48 (konsentrasi):** Hitung `top2_rev_share`, `top3_rev_share`
- **Q49 (SR threshold):** Filter `partner_table` dengan `sr < 95`

---

### SEGMENT 4 — CHANNELS

---

#### Q50. Bagaimana kondisi kesehatan ekosistem channel secara keseluruhan?

**Gunakan pendekatan sama dengan Q34 (partner health)**, namun dengan `channel_table` dan `alerts["channel"]`.

**Mapping channel:**
- `i1` = MyTelkomsel App (biasanya terbesar)
- `f0, f4, f5` = UMB (Unstructured Menu Browser)
- `b0, b3, a0` = WEC (Web/API)
- `ig` = Basic

Analisis di level **group** (App / UMB / WEC / Basic) lebih informatif dari level kode individual.

---

#### Q51. Channel mana yang mendominasi dan seberapa besar risiko konsentrasinya?

**Data:**
- `channel_table` — sortir `share` descending
- `alerts["channel"]["flagged_groups"]`

**Kalkulasi:**
- Akumulasi share top-1 group dan top-2 group
- Cek apakah satu channel group > 60% volume (risiko tinggi)

---

#### Q52. Channel mana paling efisien — value-driven atau volume-driven?

**Data:**
- `channel_table` — field `name`, `total_revenue`, `total_trx`, `share`

**Kalkulasi:**
- `rev_per_trx = total_revenue / total_trx` per channel
- Channel dengan `rev_per_trx` tinggi tapi `share` rendah = value-driven
- Channel dengan `rev_per_trx` rendah tapi `share` tinggi = volume-driven

---

#### Q53 – Q54. Channel tumbuh/turun dan distribusi produk

- **Q53:** Gunakan `channel_table.mom_trx_growth`, `alerts["channel"]["flagged"]`
- **Q54:** Ini membutuhkan cross-tab channel × produk — cek apakah `metrics` menyediakan data ini. Jika tidak tersedia, sampaikan keterbatasan data.

---

#### Q55 – Q57. Analisis Harian Channel

Sama seperti partner (Q39–Q41), gunakan `dod_alerts` filter `entity_type == "channel"` atau `"channel_group"`.

---

#### Q58 – Q63. Analisis Mingguan dan Periode Channel

Gunakan pola yang sama dengan segment partner (Q42–Q49), dengan `channel_table` dan `alerts["channel"]`.

---

### SEGMENT 5 — CROSS-SEGMENT & ROOT CAUSE

---

#### Q64. Kenapa konsentrasi ini terbentuk?

**Data yang dibutuhkan:**
- `partner_table` — top-2 partner dan share-nya
- `product_table` — top produk per partner (jika tersedia)
- `ai_insights.partner.root_cause_analysis`

**Pendekatan:**
1. Identifikasi siapa yang dominan (`partner_table.share` atau `channel_table.share`)
2. Cari apakah dominasi ini naik atau turun dibanding periode lalu (`mom_trx_growth`)
3. Cek apakah ada produk spesifik yang hanya dijual partner/channel dominan
4. Gunakan `ai_insights` untuk konteks naratif

---

#### Q65. Ke mana momentum ini mengarah?

**Data yang dibutuhkan:**
- `chart_daily_vol[-14:]` (2 minggu terakhir)
- `projection` (jika tersedia)
- `alerts["transaction"]["streak"]`
- Semua `mom_*_growth` dari partner, produk, channel

**Kalkulasi:**
- Hitung `momentum = avg(vol[-7:]) - avg(vol[-14:-7])` → apakah 7 hari terakhir lebih baik atau buruk dari 7 hari sebelumnya?
- Cek `projection.confidence` dan `projection.scenarios`

**Pola jawaban:**
```
Momentum 7 hari terakhir vs 7 hari sebelumnya: [±X]%.
[Jika projection tersedia]: Proyeksi akhir bulan: [m1_trx] trx ([confidence] confidence).
Skenario: Optimis [val] / Tengah [val] / Pesimis [val].
Arah: [Membaik / Memburuk / Stabil] — berdasarkan [streak, momentum, MoM].
```

---

## BAGIAN 4 — ATURAN OUTPUT CHATBOT

### 4.1 Struktur Jawaban Standar

Setiap jawaban mengikuti pola:

```
[VERDICT/KONDISI] — [ANGKA UTAMA] — [DETAIL/KONTEKS] — [RISIKO/REKOMENDASI jika relevan]
```

### 4.2 Yang WAJIB dilakukan

- Selalu sebut angka spesifik (persentase, jumlah, satuan)
- Selalu beri konteks waktu: "vs kemarin", "vs bulan lalu", "vs rata-rata periode"
- Gunakan format angka yang konsisten: `fmt_vol()` untuk volume, `fmt_money()` untuk revenue
- Beri verdict eksplisit: SEHAT / PERHATIAN / KRITIS dengan alasan satu kalimat

### 4.3 Yang DILARANG

- Menjawab tanpa menyebut angka ("performa cukup baik...")
- Menggunakan threshold yang tidak jelas ("naik signifikan..." — berapa %?)
- Menerka data yang tidak ada di `metrics` dict
- Mencampurkan data periode berbeda tanpa label yang jelas

### 4.4 Penanganan Data Tidak Tersedia

```
Jika field tidak ada di metrics:
→ "Data [nama field] tidak tersedia untuk periode [tanggal]. 
   Coba generate ulang dashboard dengan: python scripts/generate_dashboard_new.py --start [X] --end [Y]"

Jika LLM insights tidak tersedia:
→ Jawab dari raw data saja, tambahkan: "(Analisis AI tidak tersedia — hanya data statistik)"

Jika pertanyaan butuh cross-tab yang tidak ada:
→ "Pertanyaan ini membutuhkan data cross-tab [channel × produk] yang belum tersedia di pipeline saat ini."
```

### 4.5 Pertanyaan di Luar Cakupan Dashboard

Pertanyaan berikut **tidak dapat dijawab** dari data yang ada saat ini (butuh pengembangan tambahan):
- Forecasting/proyeksi akurat (hanya ada estimasi pace sederhana)
- Komparasi multi-periode > 2 bulan
- User behavior detail (frekuensi repeat, cohort)
- Revenue margin per produk
- Failure pattern per jam
- Channel substitution analysis

Untuk pertanyaan ini, jawab: "Pertanyaan ini membutuhkan data historis multi-periode atau analisis granular yang belum tersedia di pipeline saat ini. Ini termasuk dalam kategori Gap Analysis yang bisa dikembangkan ke depan."

---

## BAGIAN 5 — QUICK REFERENCE: FIELD PER PERTANYAAN

| # | Pertanyaan (ringkas) | Field Utama | Kalkulasi |
|---|---|---|---|
| Q1 | Volume performa | `total_vol`, `vol_wow` | Threshold MoM |
| Q2 | Revenue performa | `total_rev`, `rev_wow`, `arpu_wow` | Konsistensi arah |
| Q3 | Success Rate | `avg_sr`, `sr_wow`, `chart_daily_sr` | min_sr, hari < 95% |
| Q4 | User aktif | `total_users`, `total_users_wow` | Perbandingan arah |
| Q5 | ARPU | `arpu_val`, `arpu_wow` | Konsistensi dengan revenue |
| Q6 | DoD hari terakhir | `dod_alerts[total]`, `chart_daily_vol[-1:-2]` | vol_dod, rev_dod |
| Q7 | MoM same-date | `transaction_period.hari_ini.mom` | Langsung baca |
| Q8 | Tren 3 hari | `transaction_period.hari_ini.three_day` | trend_class |
| Q9 | Distribusi jam | `hourly_averages`, `avg_weekday_vol` | peak_hour, peak_pct |
| Q10 | Tren mingguan | `transaction_period.mingguan.weeks` | overall_chg |
| Q11 | Pola keseluruhan | `chart_daily_vol`, `alerts.transaction` | momentum, CV |
| Q12 | Anomali | `chart_daily_vol`, `period_highlights` | 2σ threshold |
| Q13 | Korelasi metrik | `vol_wow`, `rev_wow`, `sr_wow` | Arah divergensi |
| Q14 | Health portfolio produk | `product_table`, `alerts.product` | growing/declining count |
| Q15 | Konsentrasi revenue produk | `product_table.total_revenue` | top1/3/5 share |
| Q16 | Momentum terkuat produk | `product_gainers` | Langsung baca |
| Q17 | Produk tekanan | `product_losers`, `alerts.product.flagged` | Revenue impact |
| Q18 | Segmentasi nilai produk | `product_table` | rev/trx per produk |
| Q19-Q23 | Harian produk | `dod_alerts[product]` | direction, actual_value |
| Q34 | Health ekosistem partner | `partner_table`, `alerts.partner` | 5 dimensi scoring |
| Q35 | Konsentrasi partner | `partner_table.share+revenue` | top2_rev_share |
| Q36 | Momentum partner | `partner_table.mom_trx_growth` | Sort descending |
| Q37 | Risiko partner | `alerts.partner.flagged` | level, streak |
| Q38 | Efisiensi partner | `partner_table.arpu`, `revenue/trx` | ARPT per partner |
| Q39-Q41 | Harian partner | `dod_alerts[partner]` | direction, streak |
| Q50 | Health ekosistem channel | `channel_table`, `alerts.channel` | Sama dengan Q34 |
| Q51 | Konsentrasi channel | `channel_table.share` | top group share |
| Q64 | Root cause konsentrasi | `ai_insights.*.root_cause_analysis` | + data empiris |
| Q65 | Arah momentum | `chart_daily_vol[-14:]`, `projection` | momentum 7D vs 7D |

---

*Dokumen ini dibuat berdasarkan eksplorasi kodebase `ai-dashbord-settlement-master` pada Juli 2026.*
*Update dokumen ini setiap kali ada perubahan struktur `metrics` dict atau penambahan field baru di pipeline.*
