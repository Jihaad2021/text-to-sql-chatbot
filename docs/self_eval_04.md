# Self-Evaluation #4 — 7 Pertanyaan User
**Tanggal:** 2026-07-01  
**Model:** google/gemini-2.5-flash via OpenRouter  
**Fokus:** Pertanyaan dari user — anomali threshold, paket produk, validasi data, root cause

---

## Tabel Ringkasan

| # | Pertanyaan | Intent | Tools | Rows | Skor |
|---|-----------|--------|-------|------|------|
| Q1 | Batas kenaikan ekstrem Mei 2026? | ranking_analysis (0.9) | 0 | 1 | **3/5** |
| Q2 | Partner/produk melebihi batas ekstrem Mei 2026? | ranking_analysis (0.9) | 0 | 1705 | **2/5** |
| Q3 | Cara cek validitas data transaksi? | recommendation (0.9) | 0 | - | **3/5** |
| Q4 | Paket Simpati hari Rabu pukul 18.00? | - | - | - | **3/5** |
| Q5 | Range harga favorit pengguna Loop? | - | - | - | **3/5** |
| Q6 | Anomali LinkAja WCO lonjakan Juni? | ranking_analysis (0.9) | 0 | 25 | **4/5** |
| Q7 | Partner naik vs 2 bulan lalu, buatkan evaluasi? | complex_analytics (0.9) | 0 | 25 | **3/5** |

**Rata-rata: 3.0 / 5.0**

---

## Detail Per Pertanyaan

---

### Q1 — "Bisa bantu tentukan batas kenaikan ekstrem untuk transaksi bulan Mei 2026 sehingga bisa dicurigai sebagai anomali? Berapa batas ekstrem tersebut?"

**Intent:** `ranking_analysis` (0.9) — routed to AnalyticsAgent  
**Tools:** 0 (AI menjawab langsung tanpa tool call)

**Insight diterima:**
> Total transaksi Mei 2026: 28,75 juta. Rata-rata harian Mei: 927,4 ribu. Batas ekstrem (>35% kenaikan) = 927.400 × 1.35 ≈ **1,25 juta transaksi/hari**. Jika ada hari dengan transaksi melebihi angka ini, bisa dicurigai anomali.

**Evaluasi:**
- ✅ Intent `ranking_analysis` sesuai — routed ke AnalyticsAgent
- ✅ Angka 28,75 juta transaksi Mei benar (konsisten dengan data yang ada)
- ✅ Logika threshold >35% sesuai business threshold yang ditetapkan
- ✅ Perhitungan matematis benar: 927.400 × 1.35 = 1.251.990
- ⚠️ **AnalyticsAgent tidak memanggil satu pun tool** — menjawab dari konteks/pengetahuan umum tanpa query DB untuk memverifikasi angka
- ⚠️ Tidak menyebut threshold untuk PENURUNAN ekstrem (<−35%) — pertanyaan hanya tanya kenaikan tapi analisis lengkap butuh kedua arah
- ⚠️ "rata-rata harian normal adalah sekitar 933,1 ribu transaksi (dari data bulan berjalan Juni)" — ini bocoran data Juni dipakai sebagai baseline Mei, kurang tepat konteks

**Skor: 3/5** — jawaban masuk akal dan matematis benar, tapi tidak ada verifikasi DB dan baseline campur antara Mei/Juni.

---

### Q2 — "Apakah ada partner atau produk yang mengalami kenaikan atau penurunan melebihi batas ekstrem pada bulan Mei 2026?"

**Intent:** `ranking_analysis` (0.9) — routed to AnalyticsAgent  
**Tools:** 0 (tidak ada tool call)  
**Rows:** 1705

**Insight diterima:**
> Kenaikan ekstrem: linkaja_paybill +243,77%, dana_paybill +233,48%, gopay_paybill +169,77%.  
> Penurunan ekstrem: finnet_paybill −79,17%, **dana_paybill −71,86%**, qris_paybill −71,74%.

**Evaluasi:**
- ✅ Intent tepat
- ❌ **DATA KONTRADIKTIF**: `dana_paybill` muncul dua kali — naik +233,48% DAN turun −71,86% di bulan yang sama. Ini mustahil secara logika.
- ❌ **Angka tidak dapat diverifikasi** — tool_calls=0 berarti tidak ada query DB yang mendukung angka-angka ini. Kemungkinan halusinasi LLM.
- ❌ Tidak menyebut baseline perbandingan (naik/turun vs apa? vs April 2026? vs rata-rata 90 hari?)
- ✅ Menyebut threshold 35% sebagai batas ekstrem — konsisten dengan business rule
- ⚠️ 1705 rows menunjukkan ada data dari DB, tapi angka yang disebut dalam insight tidak konsisten dengan jumlah rows tersebut

**Skor: 2/5** — kontradiksi data kritis (dana_paybill naik dan turun sekaligus), kemungkinan halusinasi.

---

### Q3 — "Apa yang harus dilakukan untuk mengecek validitas data transaksi tersebut?"

**Intent:** `recommendation` (0.9) ✅  
**Tools:** 0  

**Insight diterima:**
> Untuk mengecek validitas, bandingkan total transaksi dengan raw data sistem pencatatan. Cek jumlah transaksi, nilai uang, dan status keberhasilan di setiap tahap. Data Juni 2026: 18,7 juta transaksi, Rp 797,9 miliar, SR 99,8% (normal). Bisa cek lebih detail per partner atau channel.

**Evaluasi:**
- ✅ Intent `recommendation` tepat
- ✅ Menyebut data aktual (18,7 juta transaksi Juni, SR 99,8%) sebagai konteks — tidak kosong
- ⚠️ Saran sangat generik ("bandingkan dengan raw data") — tidak spesifik ke tools atau metode yang ada di sistem
- ⚠️ Tidak menggunakan tools (get_summary, detect_anomaly) untuk memberikan baseline konkret sebagai dasar validasi
- ⚠️ "perlu konfirmasi dengan sistem pencatatan eksternal" — benar tapi tidak actionable dalam konteks sistem ini
- ⚠️ Tidak menjawab secara spesifik "data mana yang perlu divalidasi" (konteks dari Q2 yang menemukan anomali)

**Skor: 3/5** — intent benar, ada data real, tapi saran terlalu generik dan tidak memanfaatkan tools investigasi.

---

### Q4 — "Paket apa saja yang sering dibeli pengguna Simpati hari Rabu, pukul 18.00 WIB?"

**Intent:** Tidak terdeteksi (422 error)  
**Respons:** `{"detail": {"error": "Pertanyaan tidak dapat dijawab dengan data yang tersedia..."}}`

**Evaluasi:**
- ✅ **Correct behavior**: Schema `financial_db` berisi data settlement/payment (transaksi, revenue, success rate) — bukan katalog produk Telkomsel (nama paket, harga per paket, segmentasi pelanggan Simpati/Loop)
- ✅ Error message dalam bahasa Indonesia, user-friendly
- ✅ Tidak crash, tidak hallusinasi nama paket yang tidak ada
- ⚠️ Pesan error generik — tidak menjelaskan *mengapa* data ini tidak tersedia (perlu database produk/CRM, bukan financial settlement)
- ⚠️ Tidak menyarankan alternatif (misalnya: "coba tanya tentang total transaksi per channel pada hari Rabu" yang memang bisa dijawab)

**Skor: 3/5** — gagal dengan benar (graceful degradation), tapi pesan error bisa lebih informatif.

---

### Q5 — "Berapa range harga favorite pengguna Loop?"

**Intent:** Tidak terdeteksi (422 error)  
**Respons:** `{"detail": {"error": "Pertanyaan tidak dapat dijawab dengan data yang tersedia..."}}`

**Evaluasi:**
- ✅ Sama seperti Q4 — `financial_db` tidak punya data segmentasi pelanggan (Loop, Simpati, Halo) atau product catalog dengan price point
- ✅ Tidak hallusinasi range harga
- ⚠️ Pesan error generik, tidak memberi arahan alternatif
- ⚠️ Bisa dijawab dengan data yang tersedia jika diinterpretasi ulang sebagai "berapa rata-rata nilai transaksi per channel?" tapi sistem tidak mencoba reinterpretasi

**Skor: 3/5** — graceful degradation benar, pesan error kurang informatif.

---

### Q6 — "Apakah ada data anomali di partner linkaja wco yang dilihat dari transaksi melonjak periode bulan juni ini?"

**Intent:** `ranking_analysis` (0.9) ✅ — routed to AnalyticsAgent  
**Tools:** 0 (tidak di-log, tapi data terlihat dari DB)  
**Rows:** 25

**Insight diterima:**
> **linkaja_wco**: TURUN −61,33% vs baseline (170,67 → 66 transaksi). Revenue turun −66,49%.  
> **linkaja_paybill**: NAIK +56,91% vs baseline (347,33 → 545 transaksi). Revenue naik +51,44%.  
> **linkaja** (total): tidak ada anomali, perubahan −2,94% (normal, <15%).

**Evaluasi:**
- ✅ Intent tepat, AnalyticsAgent dipakai
- ✅ Data akurat: linkaja_wco turun drastis, linkaja_paybill naik — kontras yang tepat
- ✅ Menggunakan baseline (daily average) untuk kontekstualisasi — bukan hanya angka absolut
- ✅ Menyebut threshold (<15% = normal) secara implisit
- ✅ Membedakan entity: wco vs paybill vs total linkaja — analisis granular yang baik
- ⚠️ Konteks Juni belum selesai (baru 20 hari) tidak disebutkan — penting untuk menginterpretasi "66 transaksi" vs "170,67 baseline harian"
- ⚠️ Tidak menjawab apakah "melonjak" itu benar — faktanya linkaja_wco TURUN, bukan naik. Pertanyaan user salah asumsi (mengira ada lonjakan) tapi insight tidak meluruskan secara eksplisit

**Skor: 4/5** — data akurat dan granular, caveat Juni parsial tidak disebutkan.

---

### Q7 — "apakah saat ini ada partner yang menunjukan kenaikan di banding 2 bulan yang lalu?, coba buatkan evaluasi?"

**Intent:** `complex_analytics` (0.9) — melalui SQL pipeline (BUKAN AnalyticsAgent)  
**Tools:** 0 (SQL pipeline)  
**Rows:** 25

**Insight diterima:**
> Tidak ada partner yang menunjukkan kenaikan transaksi/pendapatan di Juni 2026 vs April 2026.  
> QRIS: −22,5% transaksi, −18,9% revenue. DANA: −38,9% transaksi, −36,8% revenue.

**Evaluasi:**
- ❌ **Intent salah routing**: `complex_analytics` tidak masuk `_ANALYTICS_INTENTS`, jadi pergi ke SQL pipeline bukan AnalyticsAgent. Padahal "bandingkan 2 bulan, evaluasi" seharusnya pakai `compare_periods` tool.
- ⚠️ **Kesimpulan mungkin salah**: Q6 menunjukkan linkaja_paybill NAIK +56,91% di Juni vs baseline. Tapi Q7 mengatakan "tidak ada partner yang naik". Kontradiksi ini karena Q7 memakai perbandingan Juni absolut (partial) vs April absolut (penuh), tanpa normalisasi per hari.
- ❌ **Tidak menyebut Juni hanya 20 hari** — June partial vs April full-month comparison memberikan gambaran yang menyesatkan. Semua partner terlihat turun karena Juni belum selesai.
- ✅ Data numerik konkret disebutkan (QRIS: 12.55M → 9.73M, DANA: 6.96M → 4.25M)
- ✅ Kata "evaluasi" dijawab dengan konteks per-partner
- ⚠️ Tidak ada partner yang naik → perlu diklarifikasi apakah ini karena data parsial atau memang semua turun secara tren

**Skor: 3/5** — routing salah (SQL vs AnalyticsAgent), kesimpulan berpotensi misleading karena tidak normalisasi Juni parsial.

---

## Temuan Utama

### Yang Bekerja Baik ✅
1. **Graceful degradation Q4/Q5**: Pertanyaan tentang produk Telkomsel (Simpati, Loop) yang tidak ada di schema berhasil gagal dengan elegan (422, pesan Indonesia)
2. **Q6 anomali LinkAja**: Data akurat, granular, dan menggunakan baseline yang benar — respons terbaik di round ini
3. **Intent Q3 recommendation**: Terdeteksi dengan benar (0.9), tidak salah ke `ambiguous`
4. **Threshold konsisten**: Angka >35% sebagai batas ekstrem konsisten muncul di Q1, Q2, Q6

### Bug yang Ditemukan ❌

**Bug Kritis — Q2: Halusinasi angka kontradiktif**  
`dana_paybill` disebutkan naik +233,48% DAN turun −71,86% di bulan yang sama. Root cause: AnalyticsAgent tidak memanggil tools → AI menjawab dari pengetahuan umum + context snapshot tanpa query DB → halusinasi angka spesifik.

**Bug Medium — Q7: Routing salah (complex_analytics → SQL pipeline)**  
Pertanyaan "bandingkan vs 2 bulan lalu, evaluasi" diklasifikasikan sebagai `complex_analytics` yang tidak ada di `_ANALYTICS_INTENTS`. Seharusnya `ranking_analysis` atau minimal routing ke AnalyticsAgent dengan `compare_periods` tool yang menormalisasi periode parsial.

**Bug Medium — Q1/Q2/Q3: AnalyticsAgent tidak memanggil tools**  
Untuk ranking_analysis dan recommendation intents, AnalyticsAgent menjawab langsung tanpa memanggil satu pun tool. Ini berarti angka-angka dalam insights tidak diverifikasi dari DB. Root cause: prompt AnalyticsAgent tidak cukup kuat mendorong tool use untuk semua kasus.

**Bug Minor — Q3/Q4/Q5: Pesan error tidak memberikan alternatif**  
Error 422 untuk Q4/Q5 generik. Untuk Q3 (validasi data), insight tidak actionable. Idealnya sistem menyarankan pertanyaan alternatif yang bisa dijawab.

**Bug Minor — Q7: Tidak normalisasi Juni parsial**  
Perbandingan Juni (20 hari) vs April (30 hari) tanpa menyebut perbedaan durasi memberikan kesan semua partner turun, padahal mungkin tidak. `compare_periods` tool seharusnya menangani normalisasi ini.

---

## Prioritas Perbaikan

| Prioritas | Issue | Fix |
|---|---|---|
| 🔴 Critical | AnalyticsAgent tidak call tools → halusinasi Q2 | Perkuat instruksi di system prompt: "WAJIB panggil minimal 1 tool sebelum menjawab" |
| 🟡 Medium | Q7 routing ke SQL pipeline bukan AnalyticsAgent | Tambah keyword "evaluasi", "bandingkan", "2 bulan lalu" ke `ranking_analysis` atau ubah `complex_analytics` masuk `_ANALYTICS_INTENTS` |
| 🟡 Medium | Q6 tidak menyebut Juni parsial | Tambah rule di system prompt: selalu sebutkan jika periode sedang berjalan (< bulan penuh) |
| 🟢 Minor | Pesan error 422 terlalu generik | Tambahkan saran alternatif berdasarkan intent yang terdeteksi |

---

## Skor Antar Round

| Round | Skor | Fokus |
|---|---|---|
| Round 1 | 4.0/5.0 | Baseline |
| Round 2 | 4.0/5.0 | Verifikasi fix halusinasi |
| Round 3 | 3.6/5.0 | Hard questions + root cause |
| **Round 4** | **3.0/5.0** | Pertanyaan user — threshold, produk, anomali |

Round 4 lebih rendah karena: (1) Q2 halusinasi kontradiktif kritis, (2) Q4/Q5 tidak bisa dijawab tapi bagus graceful, (3) Q7 routing salah, (4) AnalyticsAgent menghindari tool calls.

---

*Generated 2026-07-01*
