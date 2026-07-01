# Self-Evaluation #5 — Re-test Setelah 4 Fix
**Tanggal:** 2026-07-01  
**Model:** google/gemini-2.5-flash via OpenRouter  
**Fokus:** Verifikasi 4 fix dari Round 4; pertanyaan identik dengan Round 4

---

## Tabel Ringkasan

| # | Pertanyaan | Intent | Mode | Tools | Skor R4 → R5 | Δ |
|---|-----------|--------|------|-------|-------------|---|
| Q1 | Batas kenaikan ekstrem Mei 2026? | ranking_analysis (0.9) | AnalyticsAgent (cached) | get_summary (1) | 3→3.5 | +0.5 |
| Q2 | Partner/produk melebihi batas ekstrem Mei 2026? | ranking_analysis (0.9) | AnalyticsAgent (cached) | get_summary (75) | 2→3 | +1 |
| Q3 | Cara cek validitas data? | recommendation | AnalyticsAgent | — | 3→2 | **-1 REGRESI** |
| Q4 | Paket Simpati Rabu 18.00? | — | 422 error | — | 3→4 | +1 |
| Q5 | Range harga pengguna Loop? | — | 422 error | — | 3→4 | +1 |
| Q6 | Anomali LinkAja WCO Juni? | ranking_analysis (0.9) | AnalyticsAgent | detect_anomaly (25) | 4→4.5 | +0.5 |
| Q7 | Partner naik vs 2 bulan lalu, evaluasi? | complex_analytics (0.9) | AnalyticsAgent | compare_periods (25) | 3→5 | **+2** |

**Rata-rata Round 5: 3.71 / 5.0** (Round 4: 3.0 / 5.0 — naik +0.71)

---

## Detail Per Pertanyaan

---

### Q1 — Batas kenaikan ekstrem Mei 2026?

**Intent:** `ranking_analysis` (0.9) → AnalyticsAgent  
**Status:** Cached (execution_time_ms: 0.0) — hasil dari run sebelumnya post-fix  
**Tools logged in API:** null (tool_calls tidak disimpan dalam cache — lihat bug #2)

**Insight:**
> Total transaksi Mei 2026: **28,8 juta transaksi**. Batas kenaikan ekstrem (>35%): **~39 juta transaksi**.

**Evaluasi:**
- ✅ Angka real dari DB: 28,753,348 transaksi Mei (sebelum: angka dari memory/context)
- ✅ Tidak ada hallusinasi — data-backed
- ✅ Logika threshold 35% konsisten dengan business rules
- ⚠️ Threshold dihitung dari total Mei vs Mei itu sendiri (circular) — seharusnya: rata-rata harian April (baseline) × 31 hari × 1.35
- ⚠️ Hanya menghitung batas ATAS (kenaikan), tidak menyebut batas bawah (penurunan ekstrem = baseline × 0.65)
- ⚠️ tool_calls null di respons karena field tidak di-cache (bug tersendiri)

**Skor: 3.5/5** (naik dari 3/5) — data nyata, tidak hallusinasi, tapi logika baseline kurang tepat.

---

### Q2 — Partner/produk melebihi batas ekstrem Mei 2026?

**Intent:** `ranking_analysis` (0.9) → AnalyticsAgent  
**Status:** Cached  
**Tools (dari run yang di-cache):** `get_summary(all, partner+product, May)` — 75 rows

**Insight:**
> Tidak ada partner yang melebihi batas ekstrem. Telkomsel Wallet SR 95,75% (di bawah 97%). QRIS: 13,87 juta trx, Dana: 7,23 juta trx.

**Evaluasi:**
- ✅ Tidak ada kontradiksi data (Round 4: dana_paybill naik DAN turun sekaligus — bug kritis sudah hilang)
- ✅ Semua angka data-backed, tidak hallusinasi
- ⚠️ **Salah tool**: Pertanyaan "melebihi batas ekstrem" butuh perbandingan vs baseline (April → Mei) — seharusnya pakai `detect_anomaly` atau `compare_periods`, bukan `get_summary` yang hanya menampilkan absolut Mei
- ⚠️ Kesimpulan "tidak ada yang melebihi batas ekstrem" tidak bisa diverikasi hanya dari `get_summary` — perlu baseline untuk tahu naik/turunnya
- ✅ SR Telkomsel Wallet 95.75% (<97%) diidentifikasi dengan benar

**Skor: 3/5** (naik dari 2/5) — halusinasi hilang, tapi tool yang dipilih kurang tepat untuk pertanyaan ini.

---

### Q3 — Cara cek validitas data transaksi?

**Intent:** `recommendation` → AnalyticsAgent (Fix 2: routing baru)  
**Status:** ❌ **TIMEOUT** — request melebihi 180 detik

**Evaluasi:**
- ❌ **REGRESI KRITIS**: Sebelum fix, `recommendation` langsung ke SQL pipeline → respons 5-10 detik. Setelah Fix 1 (mandatory tool calls) + Fix 2 (recommendation → AnalyticsAgent), AnalyticsAgent dipaksa call tool dulu → multiple LLM call + DB query → 180s+ timeout.
- ❌ Pertanyaan "apa yang harus dilakukan?" adalah meta-question yang tidak selalu butuh DB tool call — tapi instruksi "WAJIB call 1 tool" memaksanya.
- Sebelumnya (Round 4): respons muncul (walaupun generik, skor 3/5). Sekarang tidak muncul sama sekali.

**Skor: 2/5** (turun dari 3/5) — regresi nyata: timeout lebih buruk dari jawaban generik.

---

### Q4 — Paket Simpati Rabu pukul 18.00?

**Status:** 422 error (tidak berubah)

**Pesan error baru:**
> "Database ini berisi data settlement transaksi digital (partner, channel, success rate, revenue). Data produk Telkomsel (nama paket, harga, kuota, segmentasi pelanggan Simpati/Loop/Halo) tidak tersedia di sini. Coba tanyakan: total transaksi per partner, success rate, tren revenue, atau perbandingan antar periode."

**Evaluasi:**
- ✅ Menjelaskan MENGAPA tidak bisa dijawab (skema database)
- ✅ Menyebut data apa yang ADA (partner, channel, SR, revenue)
- ✅ Memberikan saran alternatif konkret (tren revenue, perbandingan partner)
- ✅ Masih gagal secara elegan — tidak crash, tidak hallusinasi

**Skor: 4/5** (naik dari 3/5) — pesan error jauh lebih informatif dan actionable.

---

### Q5 — Range harga pengguna Loop?

**Status:** 422 error — pesan identik dengan Q4

**Evaluasi:** Sama dengan Q4. Fix keyword detection (`loop`, `simpati`, `halo`) bekerja dengan benar.

**Skor: 4/5** (naik dari 3/5) — sama.

---

### Q6 — Anomali LinkAja WCO transaksi melonjak Juni?

**Intent:** `ranking_analysis` (0.9) → AnalyticsAgent  
**Tools:** `detect_anomaly` (25 rows)  
**Execution time:** 10.008s (live run, tidak dari cache)

**Insight:**
> **linkaja_wco**: penurunan -61,33% vs baseline (66 trx), revenue -66,49% — anomali ekstrem.  
> **linkaja_paybill**: kenaikan +56,91% vs baseline (545 trx), revenue +51,44% — anomali ekstrem.  
> linkaja total, linkaja_basic, linkaja_wec: tidak ada anomali (<35% perubahan).

**Evaluasi:**
- ✅ Tool tepat: `detect_anomaly` membandingkan vs baseline harian — bukan hanya absolut
- ✅ Angka akurat dan granular (linkaja_wco -61.33%, linkaja_paybill +56.91%)
- ✅ Menggunakan threshold 35% secara eksplisit ("anomali ekstrem karena perubahannya di atas 35%")
- ✅ Membedakan sub-entity: wco vs paybill vs total linkaja
- ✅ Koreksi asumsi user: user mengira ada "lonjakan" tapi faktanya wco TURUN — insight meluruskan ini
- ⚠️ Tidak menyebut "data Juni baru 20 hari" (tapi detect_anomaly sudah normalisasi per hari ke baseline, jadi secara teknis sudah benar)

**Skor: 4.5/5** (naik dari 4/5) — hampir sempurna. Threshold eksplisit, tool tepat, koreksi asumsi user.

---

### Q7 — Evaluasi partner naik vs 2 bulan lalu?

**Intent:** `complex_analytics` (0.9) → AnalyticsAgent (FIX 2 BERHASIL)  
**Tools:** `compare_periods(Juni 2026 vs April 2026, by partner)` (25 rows)  
**Execution time:** 8.633s (live run)

**Insight:**
> **linkaja_wco**: +530,11% transaksi, +716,88% revenue (ekstrem).  
> **qris_paybill**: +91,58% transaksi, +94,12% revenue.  
> **ovo_wec**: +22,67% transaksi (meski revenue sedikit turun).  
> "Data bulan Juni ini baru mencakup **20 hari pertama**, sehingga perbandingan dengan April yang merupakan data satu bulan penuh mungkin perlu dinormalisasi berdasarkan rata-rata harian."

**Evaluasi:**
- ✅ Routing benar: `complex_analytics` → AnalyticsAgent (Fix 2 — sebelumnya SQL pipeline salah)
- ✅ Tool tepat: `compare_periods` — normalisasi built-in untuk periode berbeda
- ✅ Menemukan partner yang NAIK: linkaja_wco, qris_paybill, ovo_wec (Round 4: bilang "tidak ada yang naik" — sekarang benar)
- ✅ **Secara eksplisit menyebut "20 hari pertama"** (Fix 3 berhasil!)
- ✅ Menyarankan normalisasi rata-rata harian — sangat tepat untuk konteks ini
- ✅ Tidak hallusinasi, semua angka dari DB

**Skor: 5/5** — sempurna di semua dimensi. Improvement terbesar di round ini.

---

## Ringkasan Fix yang Berhasil ✅

| Fix | Efek |
|-----|------|
| Fix 1 — Mandatory tool call AnalyticsAgent | Q2: halusinasi kontradiktif hilang. Q6: detect_anomaly terpilih |
| Fix 2 — complex_analytics → AnalyticsAgent | Q7: compare_periods dipakai, 3 partner naik teridentifikasi (vs "tidak ada" sebelumnya) |
| Fix 3 — Partial period rule | Q7: "20 hari pertama" disebutkan secara eksplisit |
| Fix 4 — Error 422 keyword detection | Q4/Q5: pesan error spesifik dengan penjelasan + saran alternatif |

---

## Bug Baru yang Ditemukan ❌

### Bug 1 (Kritis) — Q3 Timeout: Regresi dari Fix 1+2
**Gejala:** Pertanyaan "apa yang harus dilakukan?" (recommendation intent) timeout 180+ detik.  
**Root cause:** Fix 1 (mandatory tool call) + routing recommendation ke AnalyticsAgent menyebabkan AI harus call tool sebelum menjawab. AnalyticsAgent → multiple LLM API roundtrips → 180s+. Untuk pertanyaan meta yang tidak butuh data spesifik, ini counter-productive.  
**Fix:** Beri AnalyticsAgent escape hatch untuk meta-questions: jika pertanyaan tidak memerlukan data numerik baru (sudah ada di context snapshot), boleh jawab dengan 1 tool call get_summary saja. ATAU: exclude `recommendation` dari _ANALYTICS_INTENTS dan biarkan SQL pipeline menanganinya dengan InsightGenerator.

### Bug 2 (Minor) — tool_calls tidak ada di _CACHED_FIELDS
**Gejala:** Response cached selalu menampilkan `tool_calls: null` meski AnalyticsAgent memang memanggil tools.  
**Root cause:** `_CACHED_FIELDS` di `query_cache.py` tidak menyertakan `tool_calls`.  
**Fix:** Tambahkan `"tool_calls"` ke tuple `_CACHED_FIELDS` di `src/core/query_cache.py`.

### Bug 3 (Medium) — Q2 tool selection salah
**Gejala:** "Apakah ada partner yang melebihi batas ekstrem?" → AnalyticsAgent pilih `get_summary` (absolut Mei), bukan `detect_anomaly` atau `compare_periods` (yang bisa bandingkan vs baseline).  
**Root cause:** Prompt AnalyticsAgent tidak secara eksplisit mengarahkan kata kunci "melebihi batas", "anomali", "lonjakan" ke `detect_anomaly` sebagai tool pertama.  
**Fix:** Tambahkan panduan tool selection di `_SYSTEM_PROMPT`: "Jika pertanyaan mengandung kata 'anomali', 'lonjakan', 'melebihi batas', atau 'lebih dari normal', WAJIB gunakan `detect_anomaly` sebagai tool pertama."

---

## Skor Antar Round

| Round | Skor | Fokus |
|---|---|---|
| Round 1 | 4.0/5.0 | Baseline |
| Round 2 | 4.0/5.0 | Verifikasi fix halusinasi |
| Round 3 | 3.6/5.0 | Hard questions + root cause |
| Round 4 | 3.0/5.0 | Pertanyaan user — threshold, produk, anomali |
| **Round 5** | **3.71/5.0** | Re-test setelah 4 fix |

**Net improvement Round 4→5: +0.71**

Winner terbesar: Q7 (+2.0) — complex_analytics routing ke AnalyticsAgent dengan compare_periods.  
Satu-satunya regresi: Q3 (-1.0) — timeout karena mandatory tool call + AnalyticsAgent untuk recommendation intent.

---

## Prioritas Fix Berikutnya

| Prioritas | Issue | Lokasi | Fix |
|---|---|---|---|
| 🔴 Critical | Q3 timeout — recommendation intent terlalu lambat | `pipeline.py` | Keluarkan `recommendation` dari `_ANALYTICS_INTENTS` ATAU beri time limit per tool iteration |
| 🟡 Medium | Q2 tool selection kurang tepat untuk "batas ekstrem" | `analytics_agent.py` | Tambah panduan eksplisit: kata "anomali/lonjakan/batas" → `detect_anomaly` dulu |
| 🟢 Minor | tool_calls tidak di-cache → null di cached response | `query_cache.py` | Tambah `"tool_calls"` ke `_CACHED_FIELDS` |

---

*Generated 2026-07-01 — self_eval_05*
