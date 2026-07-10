# Loan Document Review — Local RAG API

A fully local Retrieval-Augmented Generation (RAG) API for extracting structured insights from mortgage and loan PDF documents. No cloud services required — every component runs on your machine.

Upload a loan agreement, ask plain-English questions, and get cited answers grounded in the actual document text.

---

## Architecture

```mermaid
flowchart LR
    Client -->|PDF| Upload[POST /upload]
    Upload --> Extract[pdfplumber\ntext extraction]
    Extract --> Chunk[Chunker\n≤800 chars]
    Chunk --> Embed[sentence-transformers\nall-MiniLM-L6-v2\n384-dim]
    Embed --> PG[(PostgreSQL\n+ pgvector)]

    Client -->|question| Ask[POST /ask]
    Ask --> EmbedQ[Embed query]
    EmbedQ -->|cosine search| PG
    PG -->|top-k chunks| LLM[Ollama\nllama3.2]
    LLM -->|answer + citations| Client
```

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Application                   │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ /upload  │  │ /search  │  │        /ask          │  │
│  └────┬─────┘  └────┬─────┘  └──────────┬───────────┘  │
│       │              │                   │               │
│  ┌────▼─────────────────────────────────▼───────────┐   │
│  │              Services Layer                       │   │
│  │  PDFProcessor │ Chunker │ Embedder │ LLM Generator│   │
│  └────────────────────────┬──────────────────────────┘   │
│                            │                             │
└────────────────────────────┼─────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
     ┌────▼─────┐     ┌──────▼──────┐   ┌──────▼──────┐
     │PostgreSQL│     │  pgvector   │   │   Ollama    │
     │  + ORM   │     │cosine index │   │  llama3.2   │
     └──────────┘     └─────────────┘   └─────────────┘
```

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| API | FastAPI 0.128 | Async REST framework, auto-generated OpenAPI |
| ORM | SQLAlchemy 2.0 (async) | Type-safe database access with asyncpg driver |
| Database | PostgreSQL 16 + pgvector | Document/chunk storage + vector similarity index |
| PDF Extraction | pdfplumber | Text extraction with page-level position tracking |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` | 384-dimensional semantic embeddings |
| Vector Search | pgvector cosine distance | `<=>` operator over `VECTOR(384)` column |
| LLM | Ollama + llama3.2 | Local inference, no API key required |
| Config | pydantic-settings | `.env`-backed, validated at startup |
| Containers | Docker Compose | One-command local stack |

---

## Running Tests

**Unit tests** (no services required):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/ -v
```

**Full test suite** (requires PostgreSQL from Docker):

```bash
docker compose up -d db
pytest tests/ -v
```

The real sentence-transformers model is never loaded during tests — a NumPy mock replaces it. Ollama is mocked via `unittest.mock`. API tests that need the database are automatically skipped with a clear message if the Docker container is not running.

```
tests/
├── conftest.py              # shared fixtures: FakeEmbedder, PDF builder, DB setup
├── unit/
│   ├── test_pdf_processor.py   # 10 tests — extraction, page boundaries, error cases
│   ├── test_chunker.py         # 12 tests — splitting, tail merging, edge cases
│   └── test_embedder.py        # 8 tests  — init, dimensions, uninitialized fallback
└── api/
    ├── test_health.py          # 4 tests  — no DB required
    ├── test_documents.py       # 12 tests — upload, search, deduplication
    └── test_ask.py             # 10 tests — RAG answers, citations, Ollama 503
```

---

## Prerequisites

- Python 3.9+
- Docker Desktop
- ~4 GB free disk space (for the llama3.2 model)

---

## Quick Start

**1. Clone and set up the environment**

```bash
git clone <repo-url>
cd loan-rag
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**2. Configure environment**

```bash
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD at minimum
```

Key variables:

```env
DATABASE_URL=postgresql+asyncpg://loan_rag:yourpassword@localhost:5435/loan_rag
POSTGRES_PASSWORD=yourpassword
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=llama3.2
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

> **Port note:** If you have another PostgreSQL running locally (e.g. a Homebrew install), the Docker container is mapped to `5435` to avoid collision. Adjust `DATABASE_URL` accordingly.

**3. Start Docker services**

```bash
docker compose up -d db ollama
```

**4. Pull the LLM model** (one-time, ~2 GB)

```bash
docker compose exec ollama ollama pull llama3.2
```

**5. Start the API server**

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Wait for: `Application startup complete.`

The API is now live at `http://127.0.0.1:8000`.
Interactive docs: `http://127.0.0.1:8000/docs`

---

## AWS Deployment

> **Estimated cost:** ~$40–60/month (db.t3.micro RDS + t3.large EC2 + ALB + ECS Fargate).
> Terminate resources when not in use.

### Architecture

```
Internet (HTTP:80)
       ↓
 Application Load Balancer   — internet-facing, routes to ECS tasks
       ↓
  Default VPC (us-east-2)
       ├── ECS Fargate (1 vCPU / 2 GB)   FastAPI container   public subnet
       ├── RDS PostgreSQL 16 + pgvector   db.t3.micro         private subnet
       └── EC2 t3.large                   Ollama + llama3.2   public subnet, SSM only
```

No Terraform required — everything is provisioned with the AWS CLI.

### Prerequisites

- AWS CLI configured (`aws configure`)
- Docker Desktop running
- IAM permissions: `ECR`, `ECS`, `RDS`, `EC2`, `IAM`, `ElasticLoadBalancingV2`, `CloudWatchLogs`

### Deploy (one command)

```bash
export AWS_REGION=us-east-2
export DB_PASSWORD=<choose-a-strong-password>   # avoid @ / # ? characters
bash deploy/setup.sh
```

The script runs in sequence (~25 minutes, most of which is RDS provisioning) and prints the public URL when complete:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Deployment complete!

  Public API:  http://loan-rag-alb-<id>.us-east-2.elb.amazonaws.com
  Health:      http://loan-rag-alb-<id>.us-east-2.elb.amazonaws.com/api/v1/health
  Docs:        http://loan-rag-alb-<id>.us-east-2.elb.amazonaws.com/docs
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

> The first `/ask` request after deployment may be slow (1–2 minutes) while Ollama finishes pulling the llama3.2 model in the background. Subsequent requests are fast.

### View live logs

```bash
aws logs tail /ecs/loan-rag --follow --region us-east-2
```

### What the script provisions

| Resource | Name | Purpose |
|---|---|---|
| ECR repository | `loan-rag` | Docker image storage |
| IAM role | `loan-rag-ecs-execution-role` | Allows ECS to pull from ECR + write CloudWatch Logs |
| IAM role + profile | `loan-rag-ec2-ssm-role` | Allows EC2 management via SSM (no SSH key needed) |
| Security group | `loan-rag-alb-sg` | ALB: allows inbound HTTP:80 from internet |
| Security group | `loan-rag-ecs-sg` | ECS tasks: allows 8000 from ALB only |
| Security group | `loan-rag-rds-sg` | RDS: allows 5432 from ECS tasks only |
| Security group | `loan-rag-ollama-sg` | Ollama: allows 11434 from ECS tasks only |
| RDS PostgreSQL 16 | `loan-rag-db` | Document/chunk/vector storage |
| EC2 t3.large | `loan-rag-ollama` | Runs Ollama + llama3.2 |
| CloudWatch log group | `/ecs/loan-rag` | Container stdout/stderr (30-day retention) |
| ECS Fargate cluster | `loan-rag-cluster` | Container orchestration |
| ECS task definition | `loan-rag` | Container spec (1 vCPU, 2 GB RAM) |
| Application Load Balancer | `loan-rag-alb` | Internet-facing HTTP endpoint |
| ALB target group | `loan-rag-tg` | Routes to ECS task on port 8000 |
| ECS Fargate service | `loan-rag-service` | Keeps 1 task running, integrates with ALB |

### Tear down

```bash
bash deploy/teardown.sh
```

Deletes all resources in dependency order. RDS is removed without a final snapshot.

---

## API Reference

### `GET /api/v1/health`

Health and readiness probe.

```bash
curl http://localhost:8000/api/v1/health
```

```json
{
  "status": "ok",
  "app_name": "Loan Document Review",
  "environment": "development",
  "version": "0.1.0"
}
```

---

### `POST /api/v1/documents/upload`

Upload a PDF. Extracts text, splits into chunks, generates embeddings, and persists everything in a single transaction.

- **Max file size:** 20 MB
- **Accepted types:** `application/pdf`
- **Deduplication:** SHA-256 — uploading the same file twice returns `409 Conflict`

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@/path/to/loan_agreement.pdf;type=application/pdf"
```

**Response `201 Created`:**

```json
{
  "document_id": "aa588881-e5fc-4179-8989-9af116009a13",
  "filename": "loan_agreement.pdf",
  "page_count": 3,
  "char_count": 2683,
  "chunk_count": 5,
  "text_preview": "RESIDENTIAL MORTGAGE LOAN AGREEMENT\nLoan Number: RML-2024-00847\n..."
}
```

---

### `POST /api/v1/documents/search`

Semantic similarity search over all stored chunks. Returns the top-k chunks closest to the query in embedding space.

```bash
curl -X POST http://localhost:8000/api/v1/documents/search \
  -H "Content-Type: application/json" \
  -d '{"query": "interest rate", "top_k": 3}'
```

**Request body:**

| Field | Type | Default | Description |
|---|---|---|---|
| `query` | string | required | Natural language query |
| `document_id` | UUID | null | Restrict to one document |
| `top_k` | int 1–20 | 5 | Number of results |

**Response `200 OK`:**

```json
{
  "results": [
    {
      "chunk_id": "8b02cc57-890f-46dc-b44d-3e2beb593565",
      "document_id": "aa588881-e5fc-4179-8989-9af116009a13",
      "chunk_index": 2,
      "page_number": 2,
      "content": "PMI Required: Yes (LTV exceeds 80%)\nPMI Monthly Premium: $142.00\n...",
      "similarity_score": 0.3695
    },
    {
      "chunk_id": "eca4d72d-f0ca-4b0c-aa5b-acfa8c602824",
      "document_id": "aa588881-e5fc-4179-8989-9af116009a13",
      "chunk_index": 0,
      "page_number": 1,
      "content": "Loan Amount: $485,000.00\nInterest Rate: 6.875% per annum, fixed...",
      "similarity_score": 0.2682
    }
  ]
}
```

---

### `POST /api/v1/ask`

Ask a natural-language question. Retrieves the most relevant chunks via vector search, then sends them to Ollama as context for a grounded answer.

```bash
curl -X POST http://localhost:8000/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the loan amount and interest rate?", "top_k": 3}'
```

**Request body:**

| Field | Type | Default | Description |
|---|---|---|---|
| `question` | string | required | Natural language question |
| `document_id` | UUID | null | Restrict retrieval to one document |
| `top_k` | int 1–20 | 5 | Chunks passed to the LLM as context |

**Response `200 OK`:**

```json
{
  "answer": "Loan Amount: $485,000.00\nInterest Rate: 6.875% per annum, fixed for the life of the loan.",
  "citations": [
    {
      "chunk_id": "eca4d72d-f0ca-4b0c-aa5b-acfa8c602824",
      "document_id": "aa588881-e5fc-4179-8989-9af116009a13",
      "chunk_index": 0,
      "page_number": 1,
      "content": "RESIDENTIAL MORTGAGE LOAN AGREEMENT\nLoan Number: RML-2024-00847\n..."
    }
  ]
}
```

**Error responses:**

| Status | Condition |
|---|---|
| `404` | No chunks found — no documents uploaded yet |
| `503` | Ollama is not running or timed out |

---

## Data Model

```
documents
├── id (UUID PK)
├── filename, original_name
├── sha256 (UNIQUE — deduplication key)
├── page_count, file_size_bytes, mime_type
├── status  (pending | processing | ready | failed)
├── raw_text
└── processed_at

chunks
├── id (UUID PK)
├── document_id (FK → documents)
├── chunk_index  (ordered position within document)
├── content (TEXT)
├── embedding (VECTOR(384))   ← pgvector column
├── char_start, char_end      ← character offsets into raw_text
└── page_number

citations
├── id (UUID PK)
├── message_id (FK → messages)
├── chunk_id (FK → chunks)
├── similarity_score
└── rank
```

---

## Project Structure

```
loan-rag/
├── app/
│   ├── main.py               # FastAPI app, lifespan, middleware, exception handlers
│   ├── config.py             # pydantic-settings config with .env support
│   ├── models.py             # SQLAlchemy ORM models
│   ├── docs.py               # Custom dark-mode Swagger UI
│   ├── api/
│   │   └── v1/
│   │       ├── router.py     # Assembles all routers
│   │       ├── documents.py  # /upload and /search endpoints
│   │       ├── ask.py        # /ask endpoint
│   │       └── health.py     # /health endpoint
│   ├── core/
│   │   └── database.py       # Async engine, session factory, get_db dependency
│   └── services/
│       ├── pdf_processor.py  # pdfplumber extraction, page-offset mapping
│       ├── chunker.py        # Character-level chunking with clean split heuristics
│       ├── embedder.py       # sentence-transformers wrapper, thread-pool offload
│       └── answer_generator.py  # Ollama HTTP client, prompt template
├── docker-compose.yml        # PostgreSQL + pgvector, Ollama
├── Dockerfile                # Multi-stage build; bakes embedding model into image
└── .env                      # Local secrets (not committed)
```

---

## How the RAG Pipeline Works

**Ingestion (upload):**

1. PDF bytes validated (`%PDF-` magic bytes + MIME type)
2. `pdfplumber` extracts text page-by-page, tracking character offsets
3. Text split into chunks of ≤800 characters at clean boundaries (paragraph → sentence → word → hard cut)
4. All chunks embedded in one batched call to `all-MiniLM-L6-v2` running in a thread pool executor
5. `Document` + all `Chunk` rows (with `VECTOR(384)` embeddings) written in a single transaction

**Retrieval + Generation (ask):**

1. Question embedded with the same model
2. pgvector `<=>` cosine distance operator finds the top-k nearest chunks
3. Chunks assembled into a context block with page citations
4. Prompt sent to Ollama (`llama3.2`) via HTTP — model is instructed to answer only from the provided context
5. Answer and source chunks returned to the caller

---

## Challenges and Lessons Learned

**Python 3.9 + SQLAlchemy 2.0 annotation compatibility**

`from __future__ import annotations` defers all type annotations as strings. SQLAlchemy 2.0 uses `eval()` to resolve `Mapped[...]` annotations at class-creation time. In Python 3.9, `eval("int | None")` raises `NameError` because the `|` union syntax was only added in Python 3.10. The fix is explicit `Optional[T]` from `typing` throughout the models, which evaluates correctly in all Python versions.

**asyncpg `connect_args={"init": ...}` does not work with SQLAlchemy**

The asyncpg documentation shows `init` as a callback parameter for `asyncpg.create_pool()`. SQLAlchemy's async engine passes `connect_args` directly to asyncpg's lower-level `connect()` function, which does not accept `init`. This raises a `TypeError` at startup. Since pgvector ≥ 0.3.0, the `Vector` type from `pgvector.sqlalchemy` handles encode/decode at the SQLAlchemy type-processor level — no asyncpg-level codec registration is needed.

**PostgreSQL enum case mismatch**

SQLAlchemy's `Enum` type uses member *names* (`PENDING`, `PROCESSING`…) as the PostgreSQL enum values by default. The Python enum used lowercase *values* (`"pending"`, `"processing"`…) for the `server_default`. These are case-sensitive in PostgreSQL, causing `invalid input value for enum doc_status: "pending"` on every `INSERT`. Fix: `values_callable=lambda x: [e.value for e in x]` forces the PG enum to use the Python `.value` strings.

**Port collision between host PostgreSQL and Docker**

macOS Homebrew installs PostgreSQL and starts it on `localhost:5432`. Docker's port mapping for the same port creates a conflict — asyncpg connects to the local instance (no `loan_rag` role) instead of the containerized one. Remapping the Docker container to port `5435` in `docker-compose.yml` and `DATABASE_URL` resolves this without touching the host service.

**Naive vs. aware datetimes with `TIMESTAMP WITHOUT TIME ZONE`**

Passing a timezone-aware `datetime` (e.g., `datetime.now(timezone.utc)`) to asyncpg for a `TIMESTAMP WITHOUT TIME ZONE` column raises `DataError: can't subtract offset-naive and offset-aware datetimes`. PostgreSQL's `TIMESTAMP WITHOUT TIME ZONE` expects a naive datetime. Fix: use `datetime.utcnow()` (timezone-naive).

---

## Future Improvements

- **Alembic migrations** — currently schema is created via `create_all` at startup; Alembic would allow versioned, reversible schema changes
- **Conversation history** — the `conversations` and `messages` tables are modeled but not yet wired to endpoints; multi-turn Q&A with context window management
- **Document field extraction** — the `document_fields` table supports structured key/value extraction (loan amount, borrower name, etc.) as a separate extraction pass
- **Re-ranking** — a cross-encoder re-ranking step (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`) between vector retrieval and LLM generation to improve answer quality
- **Streaming responses** — Ollama supports `stream: true`; Server-Sent Events would allow the LLM answer to stream to the client token-by-token
- **Authentication** — bearer token middleware (the OpenAPI spec already documents it)
- **Tests** — pytest with `httpx.AsyncClient` against a test database; the chunker and embedder are pure functions and easy to unit test
- **Frontend** — a minimal React or HTMX UI around the three endpoints

---

## Resume Bullet

> **Loan Document Review RAG API** — Built a fully local document Q&A system using FastAPI, PostgreSQL + pgvector, and Ollama (llama3.2). Implemented a complete RAG pipeline: PDF ingestion with pdfplumber, adaptive text chunking, 384-dim semantic embeddings via sentence-transformers, cosine vector search, and grounded answer generation with source citations. Debugged and resolved four distinct SQLAlchemy/asyncpg/Python 3.9 compatibility issues including annotation evaluation, enum serialization, and datetime timezone handling.
