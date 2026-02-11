# Text-to-SQL Analytics Chatbot

AI-powered chatbot for multi-database analytics using natural language.

## Quick Start

\`\`\`bash
# 1. Setup environment
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your API keys

# 3. Setup databases
python scripts/setup_databases.py
python scripts/index_schemas.py

# 4. Run tests
python scripts/run_tests.py

# 5. Start services
uvicorn src.main:app --reload        # Terminal 1: API
streamlit run src/ui/app.py          # Terminal 2: UI
\`\`\`

## Documentation

- [Design Rationale](docs/01_DESIGN_RATIONALE.md)
- [Implementation Guide](docs/02_IMPLEMENTATION_GUIDE.md)
- [Test Strategy](docs/03_TEST_STRATEGY.md)
- [Quick Reference](docs/04_QUICK_REFERENCE.md)

## Architecture

Hybrid modular system with 7 components:
1. Intent Classifier (Agentic)
2. Schema Retriever (Traditional - RAG)
3. Retrieval Evaluator (Agentic)
4. SQL Generator (Agentic)
5. SQL Validator (Hybrid)
6. Query Executor (Traditional)
7. Insight Generator (Agentic)

## Project Structure

\`\`\`
src/                 # Source code
├── components/      # 7 pipeline components
├── models/          # Pydantic models
├── utils/           # Utilities
└── ui/              # Streamlit UI

scripts/             # Setup & testing
├── setup_databases.py
├── index_schemas.py
└── run_tests.py

tests/               # Test suite
config/              # Configuration files
docs/                # Documentation
\`\`\`

## Tech Stack

- **LLM:** Claude Sonnet 4
- **Vector DB:** ChromaDB
- **Database:** PostgreSQL
- **API:** FastAPI
- **UI:** Streamlit

## License

Proprietary - Technical Test Project
