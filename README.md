# InfraGenie

> **AI-powered infrastructure management and automation platform** — InfraGenie uses a multi-agent AI pipeline (powered by Google Gemini) to translate natural-language infrastructure requests into production-ready Terraform configurations, validate them against security and policy rule sets, estimate AWS costs, execute approved plans, and continuously monitor deployed resources — all through a real-time React dashboard.

---

## Project Structure

```
infragenie/
├── backend/           # FastAPI backend — agents, RAG, Terraform, AWS integrations
├── frontend/          # React dashboard (Create React App)
├── terraform_workspace/  # Generated Terraform HCL is written here at runtime
├── chroma_db/         # ChromaDB vector store persistence
├── knowledge/         # Markdown/text docs ingested into ChromaDB
│   ├── aws_best_practices/
│   ├── terraform_patterns/
│   └── policies/
├── docker-compose.yml
├── .env.example
├── requirements.txt
└── README.md
```

---

## Setup Instructions

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (optional, for containerised setup)
- Terraform CLI (for actual infrastructure operations)
- AWS account with appropriate IAM permissions
- Google Gemini API key

### 1. Clone the repository

```bash
git clone https://github.com/your-org/infragenie.git
cd infragenie
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in your real credentials
```

### 3a. Run with Docker Compose (recommended)

```bash
docker-compose up --build
```

- Backend available at: http://localhost:8000
- Frontend available at: http://localhost:3000
- API docs (Swagger UI): http://localhost:8000/docs

### 3b. Run locally (without Docker)

**Backend:**

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r ../requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm start
```

### 4. Load the knowledge base (optional)

Place `.md` or `.txt` documents inside `knowledge/aws_best_practices/`,
`knowledge/terraform_patterns/`, or `knowledge/policies/`, then run:

```bash
cd backend
python -c "from rag.knowledge_loader import load_knowledge_base; load_knowledge_base()"
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health check |
| WS | `/ws` | Real-time WebSocket channel |
| GET | `/docs` | Swagger UI (auto-generated) |

---

## License

MIT © InfraGenie Contributors
