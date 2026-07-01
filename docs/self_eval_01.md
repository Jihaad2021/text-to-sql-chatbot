# Self-Evaluation #1 — Text-to-SQL Chatbot
**Tanggal:** 2026-07-01  
**Model:** google/gemini-2.5-flash via OpenRouter  
**Pertanyaan:** 6 (dari mudah → sulit)

---

## Tabel Ringkasan

| # | Pertanyaan | Intent | Mode | Row Count | Waktu (ms) | Skor |
|---|-----------|--------|------|-----------|------------|------|
| 1 | Berapa total transaksi bulan Juni 2026? | aggregation | single-step | 1 | 10.688 | 4/5 |
| 2 | Partner success rate tertinggi Mei 2026? | aggregation | single-step | 25 | 8.905 | 3/5 |
| 3 | Bandingkan transaksi April vs Mei per partner | complex_analytics | multi-step | 25+25 | 11.147 | 5/5 |
| 4 | Anomali transaksi 15 Juni 2026? | root_cause_analysis | analytics tool | 25 | 12.484 | 5/5 |
| 5 | Kenapa transaksi turun Juni vs Mei? | root_cause_analysis | analytics tool | 25 | 9.206 | 5/5 |
| 6 | Tren harian GoPay Mei 2026 | complex_analytics | single-step | 31 | 9.154 | 2/5 |

**Rata-rata skor: 4.0 / 5.0**

---

## Detail Per Pertanyaan

---

### Q1 — "berapa total transaksi bulan Juni 2026?"

**Intent:** `aggregation` (confidence 1.0)  
**SQL dieksekusi:**
```sql
SELECT SUM(total_trx) AS total_transaksi
FROM daily_master
WHERE date >= '2026-06-01' AND date <= '2026-06-30';
```
**Result raw:** `{"total_transaksi": "18661674"}` (1 row)

**Insight yang dihasilkan:**
> Untuk total transaksi dari tanggal 1 Juni sampai 30 Juni 2026, kita mencatat **18,7 juta transaksi**. Berdasarkan data yang ada, kita sudah melihat **18,7 juta transaksi** dengan nilai **Rp 797,9 miliar** di bulan Juni ini. Tingkat keberhasilan transaksi kita juga sangat baik, mencapai **99,8%**. Partner dengan transaksi tertinggi bulan ini masih dipegang oleh **QRIS** dengan **9,7 juta transaksi (52,1%)**, diikuti oleh **DANA** dengan **4,2 juta transaksi (22,8%)**. Sementara itu, channel **i1** mendominasi dengan **18,0 juta transaksi (96,3%)**.

**Evaluasi:** ✅ Angka total benar (18,7 juta). ✅ Revenue dan SR muncul meski tidak diminta — ini datang dari context_snapshot, membuktikan baseline injection bekerja. ⚠️ Sedikit over-inform: user hanya tanya total transaksi tapi dapat 4 kalimat tambahan. Tidak salah, tapi bisa lebih ringkas.

**Skor: 4/5**

---

### Q2 — "partner mana yang punya success rate tertinggi bulan Mei 2026?"

**Intent:** `aggregation` (confidence 1.0)  
**SQL dieksekusi:**
```sql
SELECT partner,
       ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2) AS success_rate_pct,
       SUM(total_trx) AS total_transaksi
FROM daily_master
WHERE date >= '2026-05-01' AND date <= '2026-05-31'
GROUP BY partner
ORDER BY success_rate_pct DESC;
```
**Result:** 25 rows — banyak partner dengan SR 100%, Telkomsel Wallet terendah 95.75%

**Insight yang dihasilkan:**
> Banyak partner yang punya success rate 100% di bulan Mei 2026. Beberapa di antaranya adalah **finnet_paybill** dengan 114.132 transaksi, **dana** dengan 7,2 juta transaksi, dan **ovo_paybill** dengan 10.996 transaksi. Untuk yang sedikit di bawah 100%, ada **shopeepay_wec** dengan success rate 99,79% dari 14.961 transaksi.

**Evaluasi:** ✅ Angka benar. ✅ SQL tepat. ❌ Insight dangkal — tidak menyebutkan bahwa semua _paybill variant_ punya SR 100% (ini pola menarik). ❌ Tidak menyebutkan **Telkomsel Wallet** sebagai outlier dengan SR 95.75%, padahal itu justru temuan paling menarik. ❌ Tidak memberikan ranking yang jelas — hanya menyebut 3 dari 25 partner.

**Skor: 3/5**

---

### Q3 — "bandingkan total transaksi bulan April vs Mei 2026 per partner"

**Intent:** `complex_analytics` (confidence 0.9)  
**Mode:** multi-step (2 langkah)  
- Step 1: Fetch April 2026 per partner → 25 rows  
- Step 2: Fetch Mei 2026 per partner → 25 rows  

**Insight yang dihasilkan:**
> - **QRIS:** naik 10,5% (12,55 juta → 13,87 juta)
> - **DANA:** naik 3,9% (6,96 juta → 7,23 juta)
> - **Finnet:** naik 10,4% (2,50 juta → 2,76 juta)
> - **Gopay:** naik 2,6% (1,96 juta → 2,01 juta)
> - **Shopeepay:** naik 0,8% (1,68 juta → 1,69 juta)
> - Secara keseluruhan, semua partner utama mengalami peningkatan transaksi dari April ke Mei 2026.

**Evaluasi:** ✅ Multi-step berjalan dengan benar. ✅ % perubahan dihitung dan disajikan akurat. ✅ Angka absolut tepat. ✅ Kesimpulan keseluruhan tepat. ✅ Chart bar comparison dihasilkan. Ini adalah output terbaik dari sisi analitis.

**Skor: 5/5**

---

### Q4 — "apakah ada partner yang mengalami anomali transaksi di tanggal 15 Juni 2026?"

**Intent:** `root_cause_analysis` (confidence 0.9)  
**Tool dipanggil:** `detect_anomaly(dimension='partner', target_date='2026-06-15')`  
**Result:** 25 rows, 8 partner dengan `is_anomaly=true`

**Insight yang dihasilkan:**
> - **ShopeePay Paybill:** +72,62% (975 vs baseline 564,83)
> - **QRIS Paybill:** +71,65% (7.121 vs baseline 4.148,67)
> - **DANA Paybill:** +70,28% (1.688 vs baseline 991,33)
> - **LinkAja WCO:** +67,49%
> - **LinkAja Paybill:** +40,65%
> - **Finnet Paybill:** +39,57%
> - **OVO Paybill:** +34,22%
> - **LinkAja Basic:** +33,33%
> - Partner lain tidak menunjukkan anomali signifikan (perubahan di bawah 30%).

**Evaluasi:** ✅ Tool calling bekerja sempurna. ✅ Semua 8 anomali teridentifikasi dengan % perubahan yang akurat. ✅ Revenue juga disebutkan. ✅ Memberikan konteks "30%" sebagai threshold anomali. ✅ Pola menarik teridentifikasi: semua yang anomali adalah paybill variants (bukan main flow).

**Skor: 5/5**

---

### Q5 — "kenapa total transaksi bisa turun di bulan Juni 2026 dibanding Mei?"

**Intent:** `root_cause_analysis` (confidence 1.0)  
**Tool dipanggil:** `compare_periods(dimension='all', period_a='2026-06-01→2026-06-20', period_b='2026-05-01→2026-05-31')`  
**Result:** 25 rows

**Insight yang dihasilkan:**
> Penurunan transaksi di bulan Juni 2026 (sampai tanggal 20) dibandingkan bulan Mei 2026 terlihat signifikan. **Penurunan ini kemungkinan besar disebabkan oleh data bulan Juni yang baru terkumpul selama 20 hari, sementara data bulan Mei adalah data penuh 31 hari.**
> - **Dana:** -41,21% (7,2 juta → 4,2 juta)
> - **Finnet:** -42,09% (2,7 juta → 1,5 juta)
> - **Gopay** dan **OVO:** masing-masing -38,12% dan -43,58%
> - **linkaja_wco** justru naik 470,71%, namun volume masih kecil.

**Evaluasi:** ✅ Sangat pintar — AI mendeteksi sendiri bahwa data Juni tidak lengkap (20 hari vs 31 hari) dan menyebutkan ini sebagai root cause utama. ✅ Angka-angka perbandingan akurat. ✅ Menyoroti outlier (linkaja_wco). ✅ Tidak menyimpulkan "penurunan permanen" secara gegabah.

**Skor: 5/5**

---

### Q6 — "bagaimana tren transaksi GoPay selama bulan Mei 2026 per hari?"

**Intent:** `complex_analytics` (confidence 0.9)  
**SQL dieksekusi:**
```sql
SELECT date, SUM(total_trx), SUM(total_revenue), 
       ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2) AS success_rate_pct
FROM daily_master
WHERE partner = 'gopay' AND date >= '2026-05-01' AND date <= '2026-05-31'
GROUP BY date ORDER BY date;
```
**Result:** 31 rows (data harian lengkap) — Chart line dihasilkan ✅

**Insight yang dihasilkan:**
> Transaksi harian GoPay di bulan Mei 2026 cenderung stabil di kisaran 50.000 hingga 70.000 transaksi per hari. Puncak transaksi tertinggi terjadi pada tanggal 1 Mei dengan 68.566 transaksi, sementara transaksi terendah tercatat pada tanggal 28 Mei dengan **51.583 transaksi**. Rata-rata harian transaksi GoPay di bulan Mei adalah sekitar 60.000 transaksi.

**Evaluasi:** ✅ SQL dan data benar. ✅ Chart line dihasilkan dengan benar. ❌ **Kritis: Insight sama sekali tidak menyebut spike besar tanggal 25 Mei (132.257 transaksi — hampir 2x lipat dari rata-rata harian ~62k).** Ini adalah temuan paling penting dan malah terlewat. ❌ Angka "terendah 51.583 di tanggal 28 Mei" adalah **hallusinasi** — data asli tanggal 28 Mei adalah 60.705, dan angka 51.583 tidak ada di dataset sama sekali. ❌ "Puncak 1 Mei 68.566" juga keliru — puncak sesungguhnya ada di 25 Mei (132.257).

**Skor: 2/5** — Data benar, SQL benar, chart benar, tapi narasi insight mengandung angka yang salah dan melewatkan anomali paling jelas.

---

## Kesimpulan

### Yang Bekerja Baik ✅

1. **Intent Classification:** Semua 6 pertanyaan diklasifikasikan dengan benar (aggregation, complex_analytics, root_cause_analysis). Confidence tinggi (0.9–1.0).

2. **Query Rewriter:** Bekerja konsisten — mengubah "bulan Juni 2026" → rentang tanggal eksplisit, menambahkan nama partner 'gopay' secara eksplisit.

3. **Multi-step Pipeline (Q3):** Berjalan dengan benar. Dua query dieksekusi, hasil digabungkan, % perubahan dihitung akurat dalam narasi.

4. **Analytics Tools / Root Cause Analysis (Q4, Q5):** Sangat baik. `detect_anomaly` dan `compare_periods` dipilih dan dieksekusi tepat. AI mampu mendeteksi insight non-trivial (partial month = bukan penurunan nyata di Q5, pola paybill anomali di Q4).

5. **Context Snapshot Injection:** Terbukti aktif di Q1 — insight menyertakan revenue, SR, dan top partner meskipun SQL hanya return 1 kolom. Baseline bekerja.

6. **Chart Generation:** Line chart untuk Q6 (time series), bar chart untuk Q3 (comparison), multi-series bar untuk Q4 (anomali) — semuanya benar.

### Yang Perlu Diperbaiki ⚠️

1. **Q6 — Hallusinasi Angka dalam Insight:** Insight menyebut angka minimum 51.583 yang tidak ada di data. Ini adalah bug serius — model menghasilkan angka fiktif alih-alih membaca data aktual. **Root cause:** InsightGenerator tidak dipaksa membaca raw data baris per baris; model mengandalkan "intuisi" tentang angka minimum dan salah. **Saran fix:** Tambahkan instruksi eksplisit di prompt: "Angka spesifik (min, max, tanggal) HARUS diambil langsung dari data di atas. Dilarang mengarang angka."

2. **Q6 — Melewatkan Anomali Jelas (25 Mei spike 2x lipat):** Spike 132.257 dari rata-rata 62k adalah sinyal paling penting tapi tidak disebutkan. **Saran fix:** Tambahkan instruksi "Cari dan sebutkan outlier statistis (nilai yang menyimpang >50% dari rata-rata) dalam data time series."

3. **Q2 — Insight Dangkal untuk Data Banyak Kolom:** Dari 25 partner, hanya 4 yang disebutkan, dan Telkomsel Wallet (outlier terbawah 95.75%) tidak disorot. **Saran fix:** Instruksi "Selalu sebutkan nilai tertinggi DAN terendah ketika data diurutkan."

4. **Root Cause Analysis — Hanya 1 Tool Call (Q5):** Untuk pertanyaan "kenapa turun", AI hanya memanggil 1 tool (`compare_periods`) tanpa drill down lebih lanjut (misal: cek channel, cek product type). Multi-tool iteration belum optimal.

---

*Generated by self-evaluation fork — 2026-07-01*
