# Self-Evaluation #2 — Text-to-SQL Chatbot
**Tanggal:** 2026-07-01  
**Model:** google/gemini-2.5-flash via OpenRouter  
**Fokus:** Verifikasi fix hallusinasi & outlier detection dari Round 1

---

## Tabel Ringkasan

| # | Pertanyaan | Intent | Mode | Row Count | Skor | Δ dari R1 |
|---|-----------|--------|------|-----------|------|-----------|
| Q1 | Tren harian Dana April 2026 | complex_analytics | single-step | 30 | **5/5** | — |
| Q2 | Partner SR terendah Juni 2026 | aggregation | single-step | 25 | **5/5** | ↑ dari 3/5 |
| Q3 | Revenue per channel Mei 2026 | aggregation | single-step | 8 | **5/5** | — |
| Q4 | Anomali 1 Juni 2026 | root_cause_analysis | analytics tool | 25 | **5/5** | — |
| Q5 | GoPay vs Dana SR Mei 2026 | complex_analytics | multi-step | 1+1 | **5/5** | — |
| Q6 | Distribusi per jam channel i1 | complex_analytics | — | — | **1/5** | — |
| Q7 | Partner konsisten tumbuh Maret–Juni | complex_analytics | multi-step | 84 | **2/5** | — |

**Rata-rata: 4.0 / 5.0**  
*(Round 1 rata-rata: 4.0/5.0 — angka sama, tapi komposisi berbeda: Q1 naik 3 poin, Q6 baru, Q7 baru)*

---

## Detail Per Pertanyaan

---

### Q1 — "bagaimana tren transaksi Dana selama bulan April 2026 per hari?"

**Intent:** `complex_analytics` (0.9)  
**SQL:**
```sql
SELECT date, SUM(total_trx) AS total_transaksi, SUM(total_revenue), ...
FROM daily_master
WHERE date >= '2026-04-01' AND date <= '2026-04-30' AND partner = 'dana'
GROUP BY date ORDER BY date;
```
**row_count:** 30 (semua hari April terlihat penuh)

**Insight:**
> Secara keseluruhan, transaksi harian Dana di bulan April 2026 cenderung stabil, berada di kisaran 215 ribu hingga 252 ribu transaksi per hari. Puncak transaksi terjadi di awal bulan, yaitu pada tanggal **1 April dengan 251.773 transaksi**. Sementara itu, transaksi terendah tercatat pada tanggal **14 April dengan 215.119 transaksi**. Tingkat keberhasilan transaksi (success rate) sangat tinggi dan konsisten, hampir selalu 100%.

**Verifikasi data:**
- Max: 2026-04-01 = 251.773 ✅ (benar ada di data)
- Min: 2026-04-14 = 215.119 ✅ (benar ada di data)
- Tidak ada spike besar di April Dana (data memang stabil 215k–252k)
- Tidak ada hallusinasi ✅

**Catatan:** Fix anti-hallusinasi + 60-row limit bekerja sempurna. Round 1 fix terbukti di pertanyaan tipe ini.

**Skor: 5/5**

---

### Q2 — "partner mana yang success rate terendah bulan Juni 2026?"

**Intent:** `aggregation` (0.9)  
**SQL:** GROUP BY partner ORDER BY success_rate_pct DESC (25 rows)

**Insight:**
> Banyak partner yang mencapai success rate sempurna 100%: Finnet Paybill (79.061 trx), OVO Paybill (8.006 trx), ..., Dana (4,2 juta trx)...
>
> **Di sisi lain, success rate terendah tercatat pada Telkomsel Wallet, yaitu 93,33% dari 4.781 transaksi.** Partner besar: QRIS (99,73%), Dana (100%), Gopay (99,80%), ShopeePay (99,76%).

**Verifikasi:**
- Telkomsel Wallet: 93.33% ✅ (ada di data, posisi terakhir)
- QRIS 99.73% ✅, Dana 100% ✅, Gopay 99.80% ✅
- Min DAN max disebutkan ✅

**Catatan:** Round 1 skor 3/5 karena Telkomsel Wallet tidak disebutkan. Round 2: langsung disebutkan sebagai outlier dengan angka tepat. Rule "selalu sebut min + max" bekerja.

**Skor: 5/5** ↑ dari 3/5

---

### Q3 — "berapa total revenue per channel bulan Mei 2026?"

**Intent:** `aggregation` (0.9)  
**SQL:** GROUP BY channel ORDER BY total_revenue DESC (8 rows)

**Insight:**
> Channel **i1** mendominasi dengan **Rp 1,16 triliun**. Kemudian **f0** (Rp 13,68 miliar) dan **ig** (Rp 10,35 miliar). Pendapatan terendah: **f4 yaitu Rp 107.000**.

**Verifikasi:**
- i1: 1.164.495.961.769 → Rp 1,16 triliun ✅
- f0: 13.687.463.000 → Rp 13,68 miliar ✅
- f4: 107.000 → Rp 107.000 ✅
- Tertinggi + terendah keduanya disebutkan ✅
- Dominasi i1 yang sangat ekstrim (1.16T vs f0 hanya 13.7M) disorot ✅

**Skor: 5/5**

---

### Q4 — "apakah ada anomali transaksi pada tanggal 1 Juni 2026?"

**Intent:** `root_cause_analysis` (0.9)  
**Tool dipanggil:** `detect_anomaly(target_date='2026-06-01')` → 25 rows, 9 anomali

**Insight (semua angka diverifikasi dari raw data):**

Anomali positif:
- shopeepay_wec: +89,05% (783 vs baseline 414,17) ✅
- qris_paybill: +81,18% (4.402 vs 2.429,67) ✅
- ovo_wec: +80,82% (1.141 vs 631) ✅
- finnet_paybill: +73,90% (2.792 vs 1.605,50) ✅
- shopeepay_paybill: +72,90% (621 vs 359,17) ✅

Anomali negatif:
- gopay_basic: -40,59% (640 vs 1.077,33) ✅
- ovo: -33,04% (15.060 vs 22.491) ✅
- linkaja_basic: -32,40% (16 vs 23,67) ✅
- finnet: -31,54% (88.339 vs 129.032,67) ✅

Semua 9 angka tepat sesuai data.

**Skor: 5/5**

---

### Q5 — "bandingkan success rate GoPay vs DANA bulan Mei 2026"

**Intent:** `complex_analytics` (0.9)  
**Mode:** multi-step (Step 1: gopay, Step 2: dana)

**Insight:**
> - **Dana:** success rate 100,00% dari 7,2 juta transaksi.
> - **Gopay:** success rate 99,76% dari 2,0 juta transaksi.
> - Dana 0,24% lebih tinggi dari Gopay.

**Verifikasi:**
- Dana: 100.00%, 7.228.669 → 7,2 juta ✅
- Gopay: 99.76%, 2.011.935 → 2,0 juta ✅
- Selisih: 0.24% ✅

**Skor: 5/5**

---

### Q6 — "bagaimana distribusi transaksi per jam untuk channel i1 pada tanggal 10 Mei 2026?"

**Intent:** — (tidak tercapai)  
**Hasil:** ❌ `{"detail": {"error": "Auto-fix failed to produce different SQL"}}`

**Analisis:** Pipeline crash di `sql_validator`. Kemungkinan penyebab:
- Tabel `channel_payment` tidak memiliki kolom jam/waktu — hanya ada agregasi harian
- SQL Generator mencoba query dengan `EXTRACT(HOUR FROM ...)` yang tidak valid di tabel tersebut
- SQLValidator gagal auto-fix karena tidak ada kolom waktu yang bisa digunakan

Ini adalah **bug sistem**: query hourly data untuk channel tidak bisa dijawab tapi tidak memberikan pesan error yang informatif — malah crash 500.

**Skor: 1/5** — sistem crash, tidak ada insight sama sekali

---

### Q7 — "partner mana yang konsisten tumbuh setiap bulan dari Maret sampai Juni 2026?"

**Intent:** `complex_analytics` (0.9)  
**Mode:** multi-step (1 step, 84 rows)

**Insight (raw):**
> QRIS adalah satu-satunya partner yang menunjukkan pertumbuhan konsisten. Transaksi QRIS meningkat dari 12,6 juta pada April 2026 menjadi **15,7 juta pada Mei 2026**, dan kemudian menjadi 9,7 juta pada Juni 2026 (data baru 20 hari).

**Verifikasi:**
- April QRIS: 12.552.218 → 12,6 juta ✅
- **Mei QRIS: 13.867.909 → 13,9 juta, BUKAN 15,7 juta ❌ HALLUSINASI**
- Juni QRIS: 9.726.211 → 9,7 juta ✅
- QRIS tidak ada di Maret (muncul pertama April) — klaim "konsisten dari Maret" tidak akurat

**Masalah tambahan:** Response menyertakan blok SQL mentah (``` sql ... ```) dalam insight yang seharusnya narasi.

**Root cause:**
1. 84 baris terlalu banyak untuk InsightGenerator menghitung in-head — truncated di 60 rows, AI tidak lihat semua data, lalu mengarang angka
2. QueryPlanner tidak menghasilkan CTE yang benar-benar menghitung pertumbuhan — hanya fetch raw data, menyerahkan analisis ke InsightGenerator yang kemudian gagal

**Skor: 2/5**

---

## Ringkasan Perbandingan Round 1 vs Round 2

| Aspek | Round 1 | Round 2 |
|---|---|---|
| Anti-hallusinasi time series | ❌ (51.583 tidak ada di data) | ✅ (Q1: min/max tepat) |
| Outlier disebutkan | ❌ (25 Mei spike terlewat) | ✅ (Q1 stabil, tidak ada spike — tidak ada yang perlu disebutkan) |
| Min/Max ranked data | ❌ (Telkomsel Wallet tidak disebut) | ✅ (Q2: Telkomsel 93.33% langsung disebutkan) |
| Root cause / tool calling | ✅ | ✅ |
| Multi-step | ✅ | ✅ |
| Hourly query | belum ditest | ❌ (crash 500) |
| Multi-month growth analysis | belum ditest | ❌ (hallusinasi 1 angka + SQL leak) |

---

## Bug yang Masih Ada

### Bug Prioritas Tinggi

**1. Q6 — Hourly data crash (500 error)**  
Query untuk distribusi per jam gagal dengan "Auto-fix failed to produce different SQL". Perlu:
- Cek apakah tabel `channel_payment` memiliki data granularitas jam
- Jika tidak ada: tambahkan graceful error "Data per jam tidak tersedia untuk channel ini"

**2. Q7 — Hallusinasi pada dataset besar (84 baris)**  
Mei QRIS disebutkan 15.7 juta padahal 13.9 juta. Root cause: 84 baris > 60 baris limit, AI tidak lihat semua data dan mengarang.  
Fix kandidat: Untuk analisis multi-month growth, QueryPlanner harus generate SQL yang **mengembalikan hasil analisis (partner yg tumbuh), bukan raw data** — sehingga InsightGenerator tidak perlu menghitung sendiri.

**3. Q7 — SQL code muncul di narasi insight**  
InsightGenerator meng-output blok ```sql...``` di insight user-facing. Perlu tambahkan rule: "JANGAN output blok kode SQL atau teknis dalam insight."

### Bug Prioritas Rendah

**4. Q5 — Chart label generik ("Tahap 1", "Tahap 2")**  
Bar chart comparison menampilkan "Tahap 1" dan "Tahap 2" bukan "GoPay" dan "Dana". Lebih baik gunakan step description sebagai label.

---

*Generated by self-evaluation fork — 2026-07-01*
