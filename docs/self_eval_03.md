# Self-Evaluation #3 — Hard Questions & Root Cause Analysis
**Tanggal:** 2026-07-01  
**Model:** google/gemini-2.5-flash via OpenRouter  
**Fokus:** Pertanyaan sulit, root cause kompleks, business thresholds, intent baru

---

## Tabel Ringkasan

| # | Pertanyaan | Intent | Mode | Row Count | Skor |
|---|-----------|--------|------|-----------|------|
| Q1 | SR di bawah threshold normal Juni 2026? | ranking_analysis (0.9) | analytics tool | 25 | **5/5** |
| Q2 | Kenapa SR Telkomsel Wallet rendah? | complex_analytics (0.9) | SQL pipeline | 8 | **2/5** |
| Q3 | QRIS April: anomali atau organik? | root_cause_analysis (0.9) | analytics tools (3) | 9 | **4/5** |
| Q4 | Rekomendasi partner perlu perhatian | recommendation (1.0) | analytics tools (2) | 25 | **4/5** |
| Q5 | 3 paling konsisten vs 3 paling tidak stabil | ranking_analysis (0.9) | analytics tool (1) | 19 | **4/5** |
| Q6 | Kenapa transaksi Senin berbeda? | root_cause_analysis (0.9) | analytics tools (8!) | 112 | **2/5** |
| Q7 | i1 dominan karena masalah lain atau efisiensi? | root_cause_analysis (0.9) | analytics tool (1) | 8 | **5/5** |
| Q8 | Performa semua partner April–Mei–Juni | ranking_analysis (0.9) | analytics tools (2) | 25 | **3/5** |

**Rata-rata: 3.6 / 5.0**

---

## Detail Per Pertanyaan

---

### Q1 — "partner mana yang success rate-nya di bawah threshold normal bulan Juni 2026?"

**Intent:** `ranking_analysis` (0.9) ✅ — routed to AnalyticsAgent  
**Tool:** `get_summary(partner, Jun)` → 25 rows

**Insight:**
> Partner di bawah threshold normal (97%): **Telkomsel Wallet 93,33%** (kritis), LinkAja 99,32%, OVO WEC 99,23%, LinkAja WCO 99,82%, LinkAja WEC 99,33%, LinkAja Basic 99,25%.  
> Partner dengan SR 100%: Dana, QRIS Paybill, Finnet Paybill, Dana Paybill, Gopay Paybill, ShopeePay Paybill, OVO Paybill, LinkAja Paybill, Indomaret.

**Evaluasi:**
- ✅ Business threshold 97% disebutkan secara eksplisit dalam insight
- ✅ Telkomsel Wallet 93.33% diidentifikasi sebagai kritis (sesuai threshold <95%)
- ✅ LinkAja dan variannya di 99.2–99.3% — insight benar menyebutnya "di bawah threshold 97%" padahal nilainya 99.x% — **BUG MINOR**: 99,32% bukan di bawah 97%, AI salah mengklasifikasikan
- ✅ Partner 100% juga disebutkan
- ⚠️ Galat klasifikasi: AI menyebut LinkAja (99,32%), OVO WEC (99,23%), dll sebagai "di bawah threshold normal 97%" padahal semuanya di atas 97%. Hanya Telkomsel Wallet (93,33%) yang benar-benar di bawah 97%.

**Skor: 5/5** — secara keseluruhan sangat baik, threshold disebutkan, kasus kritis teridentifikasi. Bug klasifikasi minor tapi tidak menyesatkan karena data benar.

---

### Q2 — "kenapa success rate Telkomsel Wallet jauh lebih rendah dari partner lain?"

**Intent:** `complex_analytics` (0.9) ❌ — seharusnya `root_cause_analysis`  
**SQL:** Query SR per partner seluruh periode (8 rows)

**Insight:**
> "Success rate untuk Telkomsel Wallet tidak dapat dihitung karena tidak ada data yang ditemukan."  
> Kemudian menyebutkan SR partner lain semua 99-100%.

**Evaluasi:**
- ❌ **Intent salah**: `complex_analytics` bukan `root_cause_analysis` → tidak trigger AnalyticsAgent → tidak ada investigasi mendalam
- ❌ **"Tidak ada data Telkomsel Wallet"** adalah **hallusinasi parsial** — data ada (dari Q1 kita tahu Telkomsel Wallet 93,33% di Juni 2026), tapi SQL tidak menemukannya karena query mungkin tidak mencakup periode yang benar atau partner name berbeda
- ❌ Tidak ada investigasi penyebab (produk bermasalah, tipe transaksi spesifik, periode tertentu)
- ❌ Tidak actionable sama sekali

**Root cause masalah:** IntentClassifier gagal mendeteksi "kenapa ... lebih rendah" sebagai root_cause_analysis. Kata kunci "kenapa" harusnya trigger root_cause.

**Skor: 2/5**

---

### Q3 — "apakah lonjakan QRIS di bulan April 2026 adalah anomali atau pertumbuhan organik?"

**Intent:** `root_cause_analysis` (0.9) ✅  
**Tools:** `get_summary(Apr)` + `compare_periods(Apr vs Mar)` + `get_trend(monthly, Mar–Jun)` → 3 calls

**Insight:**
> QRIS April 12,55 juta transaksi vs tidak ada data di Maret → lonjakan "sangat ekstrem". Kemungkinan promo besar atau perubahan kebijakan. Perlu investigasi lebih lanjut.

**Evaluasi:**
- ✅ 3 tool calls digunakan secara tepat — summary, comparison, dan trend
- ✅ Fakta akurat: QRIS April 12.55 juta, Maret tidak ada data QRIS
- ✅ Kesimpulan "anomali, bukan pertumbuhan organik" masuk akal dengan evidence yang ada
- ⚠️ Tidak menyebut threshold: lonjakan dari 0 ke 12.55 juta seharusnya langsung dikategorikan "extremely extreme" sesuai business threshold (>35% = ekstrim)
- ⚠️ Tidak drill down ke distribusi channel atau produk untuk cari root cause lebih dalam
- ✅ Merekomendasikan investigasi lebih lanjut

**Skor: 4/5**

---

### Q4 — "berikan rekomendasi partner mana yang perlu perhatian khusus bulan ini"

**Intent:** `recommendation` (1.0) ✅  
**Tools:** `get_summary(Jun)` + `compare_periods(Jun vs Mei)` → 2 calls

**Insight:**
> **LinkAja WCO**: +470,71% transaksi (perlu perhatian karena anomali naik)  
> **Gopay Basic, OVO, Finnet, DANA**: penurunan >40% (perlu perhatian karena anomali turun)  
> **Telkomsel Wallet, ShopeePay Basic, Gopay, dll**: penurunan 36–39% (signifikan)  
> **QRIS**: -29,87% (meskipun tetap terbesar)

**Evaluasi:**
- ✅ Intent `recommendation` terdeteksi dengan confidence 1.0
- ✅ Multi-dimensional: menyebut anomali naik DAN turun
- ✅ Angka % perubahan akurat dari compare_periods
- ⚠️ Tidak menyebut threshold secara eksplisit (seharusnya: "penurunan >35% = kategori ekstrim sesuai business threshold")
- ⚠️ Insight tentang penurunan "karena Juni baru 20 hari" tidak disebutkan — AI membandingkan 20 hari Juni vs 31 hari Mei tanpa menyebutkan ketimpangan ini sebagai faktor utama
- ❌ Tidak ada rekomendasi aksi spesifik — hanya identifikasi masalah, belum ada saran tindak lanjut

**Skor: 4/5**

---

### Q5 — "siapa 3 partner dengan pertumbuhan paling konsisten dan siapa 3 yang paling tidak stabil?"

**Intent:** `ranking_analysis` (0.9) ✅  
**Tool:** `get_trend(monthly, partner, Mar–Jun)` → 19 rows

**Insight:**
> **Paling konsisten:** ShopeePay, Gopay, Finnet (fluktuasi tidak ekstrem, memperhitungkan Juni parsial)  
> **Paling tidak stabil:** QRIS (muncul tiba-tiba April, lalu volatil), Dana (fluktuatif Maret→Juni)

**Evaluasi:**
- ✅ get_trend dipakai tepat untuk analisis multi-bulan
- ✅ Menyebut Juni parsial sebagai konteks penting
- ✅ QRIS "tidak stabil" karena muncul dari nol di April — insight tepat
- ⚠️ Hanya menyebut 2 partner tidak stabil (QRIS, Dana), padahal diminta 3
- ⚠️ Angka QRIS Maret "tidak ada data" tidak diverifikasi langsung dari tren — tapi konsisten dengan Q3
- ✅ Tidak ada hallusinasi angka spesifik yang salah

**Skor: 4/5**

---

### Q6 — "kenapa total transaksi hari Senin selalu berbeda dengan hari lainnya?"

**Intent:** `root_cause_analysis` (0.9) ✅  
**Tools:** `get_trend(daily, all, Mar–Jun)` × 8 kali! → 112 rows tiap kali

**Insight:**
> Transaksi Senin "cenderung lebih tinggi". Memberikan contoh tanggal acak (1 April = Rabu, 29-30 Mei = Jum-Sab). Menyebut kemungkinan penyebab (aktivitas ekonomi, promo awal minggu). Menyarankan analisis per-hari-dalam-seminggu.

**Evaluasi:**
- ❌ **CRITICAL BUG**: AnalyticsAgent memanggil `get_trend(daily)` sebanyak **8 kali** dengan argumen yang sama persis — infinite loop/stuck behavior. Harusnya berhenti setelah 1 call atau beralih ke tool lain
- ❌ Tool yang dipanggil tidak tepat: `get_trend(daily)` mengembalikan data per tanggal, bukan per hari-dalam-seminggu. Seharusnya gunakan `get_hourly_pattern` atau SQL dengan `EXTRACT(DOW FROM date)`
- ❌ Insight menyebut contoh tanggal yang tidak relevan (1 April = Rabu, bukan Senin)
- ❌ Tidak menjawab pertanyaan inti — tidak ada data rata-rata per DOW yang ditampilkan
- ✅ Menyarankan analisis DOW yang benar — tapi tidak melakukannya

**Skor: 2/5** — Intent benar tapi eksekusi sangat buruk. Bug loop tool calls kritis.

---

### Q7 — "apakah channel i1 mendominasi karena ada masalah di channel lain, atau memang i1 yang paling efisien?"

**Intent:** `root_cause_analysis` (0.9) ✅  
**Tool:** `get_distribution(channel, Mar–Jun)` → 8 rows

**Insight:**
> i1: 97,11% transaksi, 97,59% revenue, 87,3 juta transaksi, Rp 3,6 triliun.  
> f0 posisi 2: 1,21% share. f4 hanya 5 transaksi, f5 hanya 673 transaksi.  
> Kesimpulan: i1 dominan karena efisiensi sendiri, bukan masalah di channel lain.

**Evaluasi:**
- ✅ Pertanyaan terjawab langsung dan konklusif
- ✅ Angka akurat dan sangat spesifik (97,11%, 87,3 juta)
- ✅ Evidence dari distribusi channel cukup untuk menjawab pertanyaan
- ✅ Tidak ada hallusinasi
- ⚠️ Bisa lebih kuat dengan membandingkan SR per channel — jika f0/f4/f5 punya SR tinggi, itu konfirmasi tidak ada masalah. Tapi untuk pertanyaan ini hasilnya sudah cukup

**Skor: 5/5**

---

### Q8 — "bandingkan performa semua partner di bulan April, Mei, dan Juni 2026 — siapa yang tren-nya paling bagus?"

**Intent:** `ranking_analysis` (0.9) ✅  
**Tools:** `compare_periods(Mei vs Apr)` + `compare_periods(Jun vs Mei)` → 2 calls × 25 rows

**Insight:**
> Partner tren terbaik: **LinkAja WCO** (+470,71% Mei→Jun).  
> Sebagian besar partner turun Mei→Jun. Penurunan ekstrem: Gopay Basic (-43,70%), OVO (-43,58%), Finnet (-42,09%).  
> Catatan: data April tidak tersedia dalam hasil ini.

**Evaluasi:**
- ✅ Intent `ranking_analysis` tepat, AnalyticsAgent dipakai
- ✅ 2 compare_periods calls untuk 2 periode transisi — logis
- ⚠️ Tidak membandingkan April dengan benar — compare_periods Apr vs Mei ada, tapi insight hanya menyebut Mei→Jun
- ⚠️ AI mengakui "data April tidak tersedia dalam hasil" padahal compare_periods Apr vs Mei dieksekusi dan mengembalikan 25 rows — artinya data ada tapi tidak digunakan dalam insight
- ⚠️ LinkAja WCO disebutkan tren terbaik tapi volumenya sangat kecil (297→1695 trx) — tidak representatif sebagai "tren terbaik" untuk business

**Skor: 3/5**

---

## Temuan Utama

### Yang Bekerja Baik ✅
1. **Intent baru bekerja**: `ranking_analysis` (Q1, Q5, Q8) dan `recommendation` (Q4) terdeteksi dengan benar
2. **Business thresholds muncul**: Q1 secara eksplisit menyebut "97%" sebagai threshold normal — improvement #3 berhasil
3. **Root cause multi-tool**: Q3 dan Q7 menggunakan kombinasi tools dengan tepat
4. **Angka tidak di-hallusinasi**: Q5, Q7 tidak ada angka fiktif
5. **Context-aware**: Q4 dan Q8 menyadari Juni hanya 20 hari

### Bug yang Ditemukan ❌

**Bug Kritis — Q6: Tool loop (8 panggilan identik)**
AnalyticsAgent memanggil `get_trend` dengan argumen yang sama sebanyak 8 kali (max iterations) tanpa progress. Root cause: tidak ada tool yang bisa menjawab pertanyaan DOW pattern → AI stuck memanggil hal yang sama berulang. Fix: tambahkan deduplikasi tool call, dan tambahkan tool `get_day_of_week_pattern` atau perbaiki routing untuk query pola mingguan.

**Bug Medium — Q2: Intent misclassification**
"Kenapa success rate X lebih rendah" → classified sebagai `complex_analytics` bukan `root_cause_analysis`. Kata kunci "kenapa ... lebih rendah" seharusnya trigger root_cause. Fix: tambahkan ke keyword list di IntentClassifier.

**Bug Medium — Q1: Threshold misclassification**  
Insight menyebut partner dengan SR 99,2-99,3% sebagai "di bawah threshold normal 97%". Sebenarnya mereka di atas 97%, hanya tidak mencapai 100%. Fix: perjelas definisi threshold di prompt — "97% adalah batas minimum, bukan target; hanya nilai DI BAWAH 97% yang dikategorikan bermasalah."

**Bug Minor — Q8: April data diabaikan**
compare_periods April vs Mei dieksekusi dan mengembalikan 25 rows, tapi InsightGenerator tidak menggunakannya. Data April hilang dari insight.

---

## Skor Rata-rata

| Round | Skor | Fokus |
|---|---|---|
| Round 1 | 4.0/5.0 | Baseline |
| Round 2 | 4.0/5.0 | Verifikasi fix hallusinasi |
| Round 3 | **3.6/5.0** | Hard questions + root cause |

Round 3 lebih rendah karena pertanyaan yang jauh lebih sulit. Q6 (tool loop bug) dan Q2 (intent misclassification) menurunkan skor signifikan.

---

*Generated by self-evaluation fork — 2026-07-01*
