---
name: Production Readiness Progress
description: Which production-readiness items have been completed and what remains
type: project
---

Refactoring project text-to-sql-chatbot ke production-ready. Dikerjakan April 2026.

## Selesai — Kritikal (Batch 1)
1. CI/CD — `.github/workflows/ci.yml` (test + lint jobs)
2. Docker — `Dockerfile`, `Dockerfile.ui`, `docker-compose.yml`, `.dockerignore`
3. Startup validation — `src/core/startup.py` + wired ke lifespan di `main.py`
4. Hardcoded URL + CORS `"*"` — `src/ui/app.py` & `src/main.py`

## Selesai — Penting (Batch 2)
5. Config terpusat — `src/core/config.py` (RRF_K, LOG_FORMAT, pool settings, semua dari env)
6. Structured logging JSON — `src/utils/logger.py` (LOG_FORMAT=json)
7. Health check komprehensif — `/health` cek DB connectivity + ChromaDB secara nyata, return 503 jika degraded
8. Rate limiting — slowapi `30/minute` per IP di `/query`, dapat dikonfigurasi via RATE_LIMIT_PER_MINUTE
9. Magic number RRF_K — dipindah ke Config, dapat di-override via env
10. Type hints lengkap — `schema_retriever.py` semua method
11. Connection pooling SQLAlchemy — pool_size, max_overflow, pool_recycle di Config + QueryExecutor
12. try/finally engine disposal — `engine.dispose()` dipanggil di lifespan shutdown, dispose on failed connect
13. Input validation database — `QueryRequest.database` divalidasi terhadap Config.DB_URLS via field_validator
14. Request ID — setiap `/query` request punya uuid, ada di response dan log

**Why:** User ingin kode siap production sebelum deploy.
**How to apply:** Cek progress ini sebelum mulai batch perubahan berikutnya.
