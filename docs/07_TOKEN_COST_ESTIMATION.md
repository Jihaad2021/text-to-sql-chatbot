# Token Cost Estimation

Panduan estimasi biaya penggunaan LLM untuk sistem text-to-SQL ini. Semua angka merupakan perkiraan berdasarkan ukuran prompt aktual dan pricing per provider per Juni 2026.

---

## Agen yang Menggunakan LLM

Dari 10 agen dalam pipeline, 8 di antaranya memanggil LLM. 2 agen non-LLM adalah **SchemaRetriever** (ChromaDB + BM25 + graph) dan **QueryExecutor** (eksekusi SQL ke PostgreSQL).

| Agen | Kapan Aktif | `max_tokens` Output | Tipe |
|---|---|---|---|
| `QueryRewriter` | Opsional (pre-pipeline) | 600 | LLM |
| `IntentClassifier` | Setiap query | 500 | LLM |
| `RetrievalEvaluator` | Jika tabel > 2 | 1 000 | LLM |
| `SQLGenerator` | Setiap query | 1 000 | LLM |
| `SQLValidator` (validate) | Jika AI validation aktif | 500 | LLM |
| `SQLValidator` (fix) | Jika SQL error | 800 | LLM |
| `QueryPlanner` | Query multi-step | 800 | LLM |
| `AnalyticalInvestigator` | Root cause analysis | 400 / iterasi | LLM |
| `InsightGenerator` | Setiap query | 1 000 | LLM |

> `ENABLE_AI_VALIDATION=false` secara default — SQLValidator tidak memanggil LLM kecuali ada SQL error.

---

## Estimasi Token per Agen

Estimasi input token diukur dari ukuran prompt template + payload state yang di-inject.

| Agen | Input (est.) | Output (tipikal) | Catatan |
|---|---|---|---|
| `QueryRewriter` | ~600 | ~150 | Konversi/klarifikasi query |
| `IntentClassifier` | ~600 | ~70 | Response terstruktur pendek |
| `RetrievalEvaluator` | ~1 000 | ~300 | Skema 3–8 tabel + query |
| `SQLGenerator` | ~2 500 | ~200 | Prompt besar: rules + skema + 7 few-shot examples |
| `SQLValidator` (validate) | ~800 | ~100 | SQL + pertanyaan original |
| `SQLValidator` (fix) | ~1 000 | ~200 | SQL + error message |
| `QueryPlanner` | ~700 | ~300 | Perencanaan multi-step |
| `AnalyticalInvestigator` | ~500 | ~200 | Per iterasi, biasanya 3–5x |
| `InsightGenerator` | ~1 200 | ~350 | Termasuk 10 baris hasil query |

---

## Pricing Provider (per Juta Token)

| Provider | Model Default | Input ($/M) | Output ($/M) |
|---|---|---|---|
| **Anthropic** | `claude-sonnet-4-20250514` | $3.00 | $15.00 |
| **OpenAI** | `gpt-4o` | $2.50 | $10.00 |
| **Google** | `gemini-1.5-flash` | $0.075 | $0.30 |
| **Groq** | `llama3-8b-8192` | $0.05 | $0.08 |

> Harga dapat berubah. Cek harga terkini di masing-masing dashboard provider.

---

## Estimasi Biaya per Query

### Skenario 1 — Simple Query (aggregation / filtered_query)

Pipeline standar: IntentClassifier → RetrievalEvaluator → SQLGenerator → InsightGenerator.

```
Input  : 600 + 1 000 + 2 500 + 1 200 = 5 300 token
Output :  70 +   300 +   200 +   350 = 920 token
```

| Provider | Biaya Input | Biaya Output | **Total** |
|---|---|---|---|
| Anthropic Claude Sonnet 4 | $0.0159 | $0.0138 | **~$0.030** |
| OpenAI GPT-4o | $0.0133 | $0.0092 | **~$0.023** |
| Gemini 1.5 Flash | $0.0004 | $0.0003 | **~$0.0007** |
| Groq Llama3-8B | $0.0003 | $0.0001 | **~$0.0004** |

---

### Skenario 2 — Multi-Step Query (complex_analytics)

Tambahan: QueryPlanner + 2 iterasi SQLGenerator ekstra + InsightGenerator multi-step prompt.

```
Input  : 5 300 (base) + 700 + 2×2 500 = 11 000 token
Output :   920 (base) + 300 +  2×200  =  1 620 token
```

| Provider | **Total per Query** |
|---|---|
| Anthropic Claude Sonnet 4 | **~$0.057** |
| OpenAI GPT-4o | **~$0.044** |
| Gemini 1.5 Flash | **~$0.001** |
| Groq Llama3-8B | **~$0.0007** |

---

### Skenario 3 — Root Cause Analysis (investigasi 3 iterasi)

Tambahan: 3× AnalyticalInvestigator + InsightGenerator versi investigation prompt (lebih panjang ~2 000 token input).

```
Input  : 5 300 (base) + 3×500 + (2 000 - 1 200) = 7 600 token
Output :   920 (base) + 3×200 + (500 - 350)      = 1 670 token
```

| Provider | **Total per Query** |
|---|---|
| Anthropic Claude Sonnet 4 | **~$0.048** |
| OpenAI GPT-4o | **~$0.036** |
| Gemini 1.5 Flash | **~$0.001** |
| Groq Llama3-8B | **~$0.0006** |

---

### Overhead Tambahan

| Kondisi | Token Tambahan (est.) | Biaya Tambahan (Claude) |
|---|---|---|
| QueryRewriter aktif | +750 total | +$0.004 |
| SQLValidator AI aktif | +900 total | +$0.005 |
| SQL error → SQLValidator fix | +1 200 total | +$0.007 |
| Conversation history (2 turn) | +400 input | +$0.001 |

---

## Proyeksi Biaya Bulanan

Asumsi distribusi query harian:

| Tipe Query | Proporsi | Biaya/Query (Claude) |
|---|---|---|
| Simple | 60% | $0.030 |
| Multi-step | 25% | $0.057 |
| Root cause | 15% | $0.048 |

**Rata-rata biaya per query (Claude Sonnet 4): ~$0.038**

| Volume Harian | Claude Sonnet 4 | GPT-4o | Gemini Flash | Groq Llama3 |
|---|---|---|---|---|
| 100 query/hari | **~$114/bln** | ~$87/bln | ~$2.1/bln | ~$1.2/bln |
| 500 query/hari | **~$570/bln** | ~$435/bln | ~$10.5/bln | ~$6.0/bln |
| 1 000 query/hari | **~$1 140/bln** | ~$870/bln | ~$21/bln | ~$12/bln |
| 5 000 query/hari | **~$5 700/bln** | ~$4 350/bln | ~$105/bln | ~$60/bln |

---

## Strategi Optimasi Biaya

### 1. Routing per agen (sudah didukung sistem)
Assign model murah untuk agen sederhana, model kuat hanya untuk agen kritis:

```env
# Agen sederhana → model murah
INTENT_CLASSIFIER_LLM=groq
INTENT_CLASSIFIER_MODEL=llama3-8b-8192

RETRIEVAL_EVALUATOR_LLM=gemini
RETRIEVAL_EVALUATOR_MODEL=gemini-1.5-flash

# Agen kritis → model terbaik
SQL_GENERATOR_LLM=anthropic
SQL_GENERATOR_MODEL=claude-sonnet-4-20250514

INSIGHT_GENERATOR_LLM=anthropic
INSIGHT_GENERATOR_MODEL=claude-sonnet-4-20250514
```

Estimasi penghematan: **40–60%** dari biaya full-Claude.

### 2. Query cache (sudah aktif)
`Config.CACHE_TTL_SECONDS = 600` — query identik dalam 10 menit tidak memanggil LLM ulang. Efektif untuk dashboard yang di-refresh sering.

### 3. Nonaktifkan AI validation di production
`ENABLE_AI_VALIDATION=false` (default) menghemat 1 LLM call per query. Aktifkan hanya untuk debugging SQL.

### 4. Batasi few-shot examples di SQLGenerator
`sql_generator.py` saat ini inject 7 contoh (`self.examples[:7]`). Mengurangi ke 3–4 contoh menghemat ~300–400 token input per query tanpa kehilangan akurasi signifikan.

### 5. Potong conversation history
`IntentClassifier` dan `InsightGenerator` menyertakan 2 turn terakhir. Untuk use case non-conversational, set `conversation_history=[]` agar tidak ada overhead.

---

## Perbandingan Kualitas vs Biaya

| Provider | SQL Accuracy | Insight Quality | Biaya Relatif |
|---|---|---|---|
| Claude Sonnet 4 | Sangat tinggi | Sangat tinggi | Mahal (1×) |
| GPT-4o | Tinggi | Tinggi | Sedang (0.75×) |
| Gemini 1.5 Flash | Sedang | Sedang | Murah (0.02×) |
| Groq Llama3-8B | Terbatas | Terbatas | Sangat murah (0.01×) |

Rekomendasi untuk production:
- **Akurasi tinggi (internal analytics):** Claude Sonnet 4 untuk semua agen, atau routing hybrid Claude + Gemini Flash.
- **Volume tinggi / cost-sensitive:** Gemini Flash untuk classifier + evaluator, Claude untuk SQL generation + insight.
- **Development/testing:** Groq atau Gemini Flash penuh untuk menekan biaya iterasi.
