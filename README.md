# Agentic Developer Platform (ADP)

ADP es una fabrica tecnica multi-agente para automatizar SDLC: toma tickets del backlog, los descompone en tasks, enruta cada task al modelo adecuado, evalua el output con gobernanza multi-capa y deja trazabilidad completa para rollback y auditoria.

## Stack

- Backend: FastAPI
- Frontend: React
- Persistencia: PostgreSQL / Supabase
- Routing LLM: LiteLLM
- Testing: pytest + Jest

## Instalacion local

### Backend

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

## Ejecutar tests

### Backend

```bash
pytest tests/ --cov=app --cov-report=html
```

### Frontend

```bash
cd frontend
npm test -- --coverage
```

## Levantar entorno local

### Backend

```bash
python -m uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm run dev
```

## Documentacion relacionada

- [CONTEXT.md](CONTEXT.md)
- [ADRs.md](ADRs.md)
- [DEPLOYMENT.md](DEPLOYMENT.md)

