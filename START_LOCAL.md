# ADP — Local Development Quick-Start

## Prerequisites (verified)
- Python 3.14.0
- Node.js v24.12.0 / npm 11.11.1
- `venv/` created and deps installed
- `frontend/node_modules/` installed

---

## BEFORE STARTING — Fill in `.env`

The `.env` file exists but all keys are empty. Fill these before running:

```env
DATABASE_URL=postgresql+asyncpg://postgres:<your-password>@db.ftzxurbxqqaxcmgsbtbv.supabase.co:5432/postgres
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIzaSy...
OPENAI_API_KEY=sk-proj-...
```

---

## Step 0 — Apply DB Migrations (one-time)

Run after filling `DATABASE_URL` in `.env`:

```bash
# From project root (activate venv first)
venv\Scripts\activate
alembic upgrade head
```

Expected output: `Running upgrade -> 001, initial_schema`

---

## Terminal 1 — Backend (FastAPI)

```bash
# From project root
venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

URLs:
- API:      http://localhost:8000
- Swagger:  http://localhost:8000/docs
- ReDoc:    http://localhost:8000/redoc
- Health:   http://localhost:8000/health
- Models:   http://localhost:8000/health/models

---

## Terminal 2 — Frontend (React)

```bash
cd frontend
npm start
```

URL: http://localhost:3000

---

## Terminal 3 — Monitor Logs

Watch backend logs in Terminal 1 (uvicorn outputs to stdout).

To filter for errors only:
```bash
# In a separate shell
venv\Scripts\activate
uvicorn app.main:app --reload --port 8000 2>&1 | findstr /I "ERROR WARNING"
```

---

## Optional — Model Health Check

Verifies all 3 LLM API keys respond (no DB required):

```bash
venv\Scripts\activate
python scripts/check_models.py
```

---

## Run Tests

```bash
venv\Scripts\activate
pytest tests/ --cov=app -v
# Current result: 21 passed, 74% coverage
```

---

## Kill Servers

- Backend: `Ctrl+C` in Terminal 1
- Frontend: `Ctrl+C` in Terminal 2

If ports are stuck:
```bash
# Kill port 8000 (backend)
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Kill port 3000 (frontend)
netstat -ano | findstr :3000
taskkill /PID <PID> /F
```

---

## Current Status

| Component      | Status  | Notes                              |
|----------------|---------|------------------------------------|
| Backend deps   | READY   | venv + pip install done            |
| Frontend deps  | READY   | node_modules installed             |
| DB migrations  | PENDING | Fill DATABASE_URL in .env first    |
| Model APIs     | PENDING | Fill API keys in .env first        |
| Tests          | PASSING | 21/21 passed, 74% coverage         |
