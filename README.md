# Agentic Developer Platform (ADP) v0.1

ADP es una fabrica tecnica multi-agente para acelerar el ciclo completo de desarrollo de software. En lugar de tratar un ticket como una tarea manual aislada, el sistema lo convierte en una unidad orquestada: persiste el requerimiento, lo descompone en tasks, asigna cada task al agente adecuado, valida el resultado con reglas de gobernanza y deja trazabilidad completa para auditoria, rollback y evolucion del proyecto.

El flujo operativo es simple desde fuera y estricto por dentro. Un ticket entra desde CRM o backlog, se almacena en PostgreSQL, se asignan tasks con un modelo responsable y el `TaskExecutor` ejecuta la ruta adecuada via LiteLLM. Despues de generar codigo o artefactos, el `EvaluationEngine` aplica un gate multi-capa de seguridad, calidad, compliance y reliability antes de permitir que la tarea quede realmente completada.

ADP no esta pensado solo para generar codigo rapido. Esta diseñado para generar codigo gobernado. Cada ejecucion registra sesiones de agente, snapshots de `CONTEXT.md`, resultados de evaluacion, y estado transaccional para que una falla no deje el sistema en un estado parcial. Eso convierte al repositorio en una base para SDLC asistido por agentes con control operativo real.

El beneficio clave es compresion radical del tiempo de entrega: un flujo que normalmente requeriria coordinacion manual entre backlog, arquitectura, implementacion, QA y compliance puede ejecutarse de forma automatizada y repetible. La meta del proyecto es llevar el SDLC a un orden de magnitud superior en velocidad, con una aspiracion de 100x cuando el pipeline multi-agente esta completamente instrumentado.

## Arquitectura

```text
CRM / Backlog
      |
      v
Tickets + Tasks (PostgreSQL / Supabase)
      |
      v
FastAPI Orchestrator
      |
      v
LiteLLM Router
      |
      +--> Gemini      -> UI / frontend tasks
      +--> Claude      -> backend / orchestration tasks
      +--> GPT-4o      -> security / tests / evaluation tasks
      |
      v
Evaluation Engine
  - Security
  - Code Quality
  - Compliance
  - Reliability
      |
      +--> PASS -> task completed + audit trail + git/context checkpoint
      +--> FAIL -> task failed + rollback_context
      |
      v
Database + Git + CONTEXT.md
```

## Stack Tecnico

- Backend: FastAPI + SQLAlchemy 2.0 + Alembic + LiteLLM
- Frontend: React 18 + Vite + Tailwind CSS
- Base de datos: Supabase sobre PostgreSQL
- Persistencia runtime: `asyncpg` para la app y `psycopg2` para migraciones
- Agentes soportados via LiteLLM: Gemini 2.5 Flash, Claude, GPT-4o
- Defaults actuales del repo: Gemini 2.5 Flash, Claude Sonnet 4.6, GPT-4o
- Evaluacion multi-capa: Security + Code Quality + Compliance + Reliability
- Testing: pytest + pytest-asyncio + pytest-cov + Jest/RTL
- Observabilidad operativa: `agent_sessions`, `evaluations`, `rollback_stack`, `CONTEXT.md`

## Instalacion Local

### Prerequisitos

- Python 3.10+
- Node.js 20+
- `git`
- Acceso a una base PostgreSQL / Supabase
- Credenciales de modelos si vas a usar routing real

### 1. Clonar y entrar al proyecto

```bash
git clone <repo-url>
cd "Agentic Developer Platform (ADP)"
```

### 2. Configurar backend

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configurar frontend

```bash
cd frontend
npm install
cd ..
```

### 4. Configurar `.env`

Crea o actualiza `.env` en la raiz del proyecto con al menos:

```env
DATABASE_URL=postgresql+asyncpg://postgres:<password>@aws-1-eu-west-3.pooler.supabase.com:5432/postgres
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
OPENAI_API_KEY=...
LITELLM_MASTER_KEY=
SQL_ECHO=false
APP_ENV=development
```

Notas:
- La app usa `postgresql+asyncpg://` en runtime.
- Alembic convierte automaticamente la URL a `postgresql://` para migraciones sync.
- Si la password contiene `%`, el escape ya esta manejado en `alembic/env.py`.

### 5. Aplicar migraciones

```bash
venv\Scripts\activate
alembic upgrade head
```

## Levantar Localmente

### Terminal 1: Backend

```bash
venv\Scripts\activate
python -m uvicorn app.main:app --reload --port 8001
```

### Terminal 2: Frontend

```bash
cd frontend
npm run dev -- --port 5174
```

### URLs utiles

- Dashboard: `http://localhost:5174`
- API: `http://localhost:8001`
- Swagger: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`
- Health: `http://localhost:8001/health`
- Health de modelos: `http://localhost:8001/health/models`

## Como Usar el Sistema

### 1. Crear un ticket en la base de datos

Inserta un ticket en `tickets` y sus tasks asociadas en `tasks`. El modelo de datos ya soporta:

- `tickets`: requerimiento principal
- `tasks`: unidades de ejecucion por agente
- `evaluations`: resultados del gate de gobernanza
- `agent_sessions`: auditoria de invocaciones LLM
- `rollback_stack`: snapshots para recovery

### 2. Abrir el dashboard

Levanta el frontend y revisa los tickets disponibles. El dashboard minimo permite listar tickets, ver tasks y ejecutar acciones operativas sobre ellas.

### 3. Ejecutar una task via API

```bash
curl -X POST http://localhost:8001/api/tasks/<task_id>/execute
```

### 4. Consultar el detalle de una task

```bash
curl http://localhost:8001/api/tasks/<task_id>
```

### 5. Ejecutar evaluacion de salida

```bash
curl -X POST http://localhost:8001/api/evaluations/<task_id> ^
  -H "Content-Type: application/json" ^
  -d "{}"
```

### 6. Monitorear evaluaciones

```bash
curl http://localhost:8001/api/evaluations/<task_id>
```

## Testing

### Backend

```bash
venv\Scripts\activate
pytest tests/ --cov=app --cov-report=html
```

Objetivo minimo backend:
- Coverage >= 70%
- Ejecucion local corta y con mocks, sin llamadas reales a LLM

### Frontend

```bash
cd frontend
npm test -- --coverage
```

Objetivo minimo frontend:
- Coverage >= 50%
- Tests unitarios y de componentes con mocks

## Estructura del Proyecto

```text
ADP/
|-- app/
|   |-- agents/
|   |-- api/
|   |-- evaluators/
|   |-- models/
|   `-- services/
|-- frontend/
|   |-- public/
|   `-- src/
|-- alembic/
|   `-- versions/
|-- tests/
|-- scripts/
|-- docs/
|-- CONTEXT.md
|-- ADRs.md
|-- DEPLOYMENT.md
|-- README.md
`-- requirements.txt
```

Nota: `docs/` representa el espacio recomendado para documentacion adicional de producto, runbooks y material operativo a medida que el proyecto crezca.

## Documentacion Relacionada

- [CONTEXT.md](CONTEXT.md): estado actual del proyecto, avances, ownership y contexto operativo
- [ADRs.md](ADRs.md): decisiones arquitectonicas congeladas y restricciones del sistema
- [DEPLOYMENT.md](DEPLOYMENT.md): guia de despliegue a entornos productivos
- [START_LOCAL.md](START_LOCAL.md): quick-start local operativo

## Contribuir

### Agregar nuevos agentes

1. Define el modelo y su rol en la configuracion central.
2. Extiende el fallback chain en `app/config.py`.
3. Ajusta prompts y reglas de routing en `app/agents/`.
4. Asegura logging en `agent_sessions`.
5. Añade tests del router y fallback.

### Agregar nuevas evaluaciones

1. Crea un nuevo evaluator en `app/evaluators/`.
2. Integra el pilar en `app/services/evaluation_engine.py`.
3. Define findings consistentes con severidad y categoria.
4. Persiste resultados en `evaluations`.
5. Cubre happy path y failure path en `tests/test_evaluator.py`.

### Reglas practicas para contribuir

- No hardcodear secretos
- No marcar tasks como `completed` sin evaluacion previa
- Mantener trazabilidad de cambios en `CONTEXT.md`
- Preferir cambios pequenos, testeables y auditables

## Proximos Pasos

### Roadmap v0.2

- CRUD completo de tickets desde API y dashboard
- Creacion automatica de tasks desde ticket intake
- Mejoras de UX del dashboard y filtros por estado
- Mayor cobertura de testing end-to-end

### Roadmap v1.0

- Pipeline multi-agente totalmente autonomo
- Evaluacion paralela con politicas configurables
- Integracion real con CRM / Jira / Linear
- Deploy productivo con observabilidad y alertas
- Gobierno de prompts, coste y rendimiento por agente

## Estado

ADP v0.1 esta completado como baseline funcional local. El sistema ya incluye orquestacion backend, routing multi-modelo, evaluacion multi-capa, dashboard inicial, testing con mocks y documentacion de despliegue.
