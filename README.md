# Agentic Developer Platform (ADP)

## La fabrica tecnica multi-agente para acelerar el SDLC

ADP convierte un backlog tradicional en un pipeline de ingenieria automatizado. En lugar de pasar un ticket manualmente entre PM, backend, frontend, QA y seguridad, el sistema lo toma como entrada, lo descompone en tareas ejecutables, asigna cada tarea al agente correcto, valida el resultado y deja trazabilidad completa en base de datos, contexto y Git.

La propuesta de valor es directa: menos coordinacion manual, menos tiempos muertos y mas throughput de entrega. ADP orquesta agentes especializados para frontend, backend, testing y seguridad, y aplica una capa obligatoria de gobernanza antes de considerar una tarea como completada. No es un generador de codigo aislado; es una cadena de produccion tecnica con control operativo.

En 6 horas se construyo un baseline funcional de extremo a extremo: schema de datos, router agnostico de modelos, orquestador de tareas, framework de evaluacion multi-capa, dashboard React, tests con mocks y pipeline CI/CD. El resultado es una base lista para evolucionar hacia un SDLC semiautonomo o totalmente autonomo.

Para una empresa, el beneficio clave no es solo "programar mas rapido". Es reducir friccion estructural: menos handoffs, menos retrabajo, menos estados parciales, menos dependencia de una sola persona y mejor capacidad de escalar entregas con gobernanza, auditoria y rollback automatico.

## Que construimos en 6 horas

ADP v0.1 ya opera como una "fabrica tecnica multi-agente":

```text
Backlog / Ticket
       |
       v
Router Inteligente
       |
       +--> Agente UI / Frontend
       +--> Agente Backend / Logic
       +--> Agente QA / Security
       |
       v
Validacion Multi-Capa
       |
       +--> PASS -> DB + Git + CONTEXT actualizado
       +--> FAIL -> rollback + estado failed
       |
       v
PostgreSQL / Supabase + Git automatico
```

Sin intervencion humana en los pasos intermedios.

### Las 6 tareas completadas

| Task | Entrega | Tiempo | Modelo |
|---|---|---:|---|
| #1 | DB Schema + ORM (6 tablas) | 30 min | Claude |
| #2 | LiteLLM Router agnostico | 45 min | Claude |
| #3 | Task Executor + Context Manager | 60 min | Claude |
| #4 | Evaluation Framework (4 pilares) | 45 min | Codex |
| #5 | React Dashboard | 45 min | Gemini |
| #6 | Tests + CI/CD | 30 min | Codex |

Total aproximado de desarrollo efectivo: 4h 45m.

## Estado operativo actual

El baseline ya incluye `SmartRouter` para detectar paralelizacion y `TaskExecutor` para ejecutar waves por dependencias. La validacion E2E mas reciente se hizo contra un ticket real en PostgreSQL:

- Ticket solicitado en el encargo: `0e75d3af-40f3-4f03-93df-eeff7290348`
- Ticket real encontrado en BD y validado: `0e75d3af-40f3-4f03-93df-eeff72903487`
- Descripcion validada: "Create a React dashboard with user list, advanced filters, pagination, and API integration with backend validation"
- Resultado: `Frontend`, `Backend API` y `Database` paralelos; `Tests` secuencial; `Backend API` camino critico
- Suite real: `tests/test_e2e_smart_router_real_ticket.py`

## Arquitectura de negocio y tecnica

```text
CRM / Backlog / PM
        |
        v
Tickets + Tasks
PostgreSQL / Supabase
        |
        v
FastAPI Orchestrator
        |
        v
LiteLLM Router
        |
        +--> Gemini / UI
        +--> Claude / Backend
        +--> GPT-4o / QA + Security
        |
        v
Evaluation Engine
  - Security
  - Code Quality
  - Compliance
  - Reliability
        |
        +--> Passed -> task completed + audit trail + git checkpoint
        +--> Failed -> rollback + mark failed + retry strategy
        |
        v
CONTEXT.md + Git + Agent Sessions + Evaluations
```

## Lo que hace el sistema

### 1. Intake y descomposicion

El sistema recibe un ticket desde backlog o CRM, lo persiste y lo descompone en `tasks`. Cada task queda asociada a un agente responsable y a una cadena de dependencias.

### 2. Routing inteligente

El router decide que modelo ejecutar segun la naturaleza de la tarea. UI y componentes pueden ir a Gemini, backend y logica a Claude, y testing o security review a GPT-4o. Todo esto se abstrae con LiteLLM para evitar lock-in de proveedor.

### 3. Ejecucion controlada

Antes de ejecutar, ADP toma snapshot de `CONTEXT.md`, valida dependencias y registra la sesion del agente. Si el modelo falla o produce un output invalido, el sistema puede revertir el estado sin dejar residuos parciales.

Con `SmartRouter`, cuando el ticket lo permite, las tareas se agrupan en waves y se ejecutan con `asyncio.gather()` dentro de cada wave. El caso fullstack validado actualmente separa `Frontend`, `Backend API` y `Database` en paralelo, y deja `Tests` para una wave posterior.

### 4. Validacion multi-capa

Cada output pasa por un framework de evaluacion obligatorio:

- `SECURITY`: SQL injection, XSS, hardcoded secrets, crypto inseguro
- `CODE_QUALITY`: type safety, coverage, linting, complejidad
- `COMPLIANCE`: GDPR, ISO 27001, politicas internas
- `RELIABILITY`: edge cases, reproducibilidad, determinismo

Si falla un pilar, la tarea no se completa.

### 5. Trazabilidad total

Cada ejecucion queda registrada en:

- `tasks`
- `evaluations`
- `rollback_stack`
- `agent_sessions`
- `CONTEXT.md`
- commits Git

Eso permite auditoria, recovery y mejora continua.

## Stack tecnico

- Backend: FastAPI + SQLAlchemy 2.0 + Alembic + LiteLLM
- Frontend: React 18 + Vite + Tailwind CSS
- Base de datos: Supabase sobre PostgreSQL
- Runtime DB: `asyncpg`
- Migrations: `psycopg2`
- Testing backend: pytest + pytest-asyncio + pytest-cov
- Testing frontend: Jest / Testing Library
- Gobernanza: evaluacion de seguridad, calidad, compliance y reliability

## Los 3 agentes

ADP esta construido para ser agnostico de proveedor. La capa LiteLLM permite cambiar modelos con una linea de configuracion.

| Agente | Especialidad | Perfil de uso |
|---|---|---|
| Gemini | UI / UX / Frontend | componentes, vistas, experiencia visual |
| Claude | Backend / APIs / Orquestacion | logica de negocio, servicios, arquitectura |
| GPT-4o | Tests / Security / Compliance | testing, evaluacion, guardrails |

El sistema soporta fallback automatico. Si un modelo falla por timeout, rate limit o error transitorio, la tarea puede escalar al siguiente modelo del chain configurado.

## Evaluacion multi-capa

```text
Output generado
     |
     +--> SECURITY
     +--> CODE_QUALITY
     +--> COMPLIANCE
     +--> RELIABILITY
     |
     +--> PASS -> guardar, completar, auditar
     +--> FAIL -> rollback, fail, reintento controlado
```

Este gate es el nucleo de la propuesta empresarial: velocidad sin perder control.

## Rollback automatico y zero partial states

ADP no asume que un output de agente es confiable por defecto. Antes de ejecutar:

1. Se guarda snapshot del contexto.
2. Se ejecuta el agente.
3. Se valida el output.
4. Se decide:

- `PASSED`: commit logico, persistencia, actualizacion de estado
- `FAILED`: restauracion, estado `failed`, recovery sin basura operativa

El principio es simple: o se guarda todo, o no se guarda nada.

## Ejemplo de flujo completo

Caso: "Crear LoginForm"

1. PM crea el ticket en backlog.
2. ADP lo persiste como ticket y task.
3. El router decide: tarea UI -> agente frontend.
4. El agente genera `LoginForm.tsx`.
5. ADP guarda snapshot previo.
6. El framework valida seguridad, calidad, compliance y reliability.
7. Si pasa, marca la task como `completed`.
8. Registra sesiones, findings, contexto y commit.
9. El PM ve `DONE` en dashboard.

Ese es el valor real: el sistema avanza solo entre intake y entrega validada.

## ROI y valor de negocio

### Antes

- equipos coordinando manualmente backlog, desarrollo, QA y seguridad
- multiples handoffs
- alto coste de contexto
- tiempos muertos entre etapas
- fallos detectados tarde

### Con ADP

- setup inicial corto
- pipeline replicable
- capacidad de multiplicar throughput
- coste marginal muy bajo por feature
- trazabilidad y rollback desde el diseno

Estimacion objetivo del sistema:

- pasar de entregas limitadas por capacidad humana a un pipeline con 100+ features/mes
- reducir coste estructural frente a equipos que dependen de handoffs manuales
- mantener una huella de infraestructura muy inferior al coste salarial de una operacion equivalente

No es una promesa de marketing vacia. La arquitectura ya implementa los mecanismos base que hacen eso posible: routing, evaluacion, sesiones, rollback, persistencia y dashboard.

## Estado actual del producto

### Backend

```text
app/
  agents/
    litellm_router.py
    prompts.py
  api/
    tasks.py
    evaluations.py
  evaluators/
    security_evaluator.py
    quality_evaluator.py
    compliance_evaluator.py
  services/
    task_executor.py
    context_manager.py
    evaluation_engine.py
  models/
    schemas.py
  database.py
```

### Frontend

```text
frontend/
  src/
    components/
      TicketList.tsx
      TicketDetail.tsx
      TaskCard.tsx
    pages/
      Dashboard.tsx
    api/
      client.ts
    App.tsx
```

### Base de datos

- `tickets`
- `tasks`
- `evaluations`
- `rollback_stack`
- `adrs`
- `agent_sessions`

## URLs locales

- Dashboard: `http://localhost:5174`
- API Swagger: `http://localhost:8001/docs`
- Health Check: `http://localhost:8001/health`
- Health Models: `http://localhost:8001/health/models`

## Instalacion local

### Prerequisitos

- Python 3.10+
- Node.js 20+
- `git`
- acceso a PostgreSQL / Supabase
- credenciales de proveedor LLM si vas a probar routing real

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
cd ..
```

### `.env`

```env
DATABASE_URL=postgresql+asyncpg://postgres:<password>@aws-1-eu-west-3.pooler.supabase.com:5432/postgres
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
OPENAI_API_KEY=...
LITELLM_MASTER_KEY=
SQL_ECHO=false
APP_ENV=development
```

### Migraciones

```bash
venv\Scripts\activate
alembic upgrade head
```

## Levantar localmente

### Terminal 1

```bash
venv\Scripts\activate
python -m uvicorn app.main:app --reload --port 8001
```

### Terminal 2

```bash
cd frontend
npm run dev -- --port 5174
```

## Testing

- Backend: `pytest tests/ --cov=app --cov-report=html`
- Frontend: `npm test -- --coverage`
- Baseline actual comunicado: 21 tests, 74% coverage backend

### E2E SmartRouter con ticket real

Este test no crea tickets ni tasks. Lee un ticket real desde PostgreSQL y valida el flujo de deteccion de componentes, dependencias, paralelizacion y reporte.

1. Exporta `DATABASE_URL` antes de ejecutar el test real.
2. Ejecuta `pytest tests/test_e2e_smart_router_real_ticket.py -v -s`.
3. Verifica que el ticket cargado sea `0e75d3af-40f3-4f03-93df-eeff72903487`.

En este repositorio, `app.database` construye el engine desde `os.environ` y no desde `get_settings()`, asi que si `DATABASE_URL` no esta exportado el runtime intentara conectar a `localhost:5432`.

## Documentacion generada

- [CONTEXT.md](CONTEXT.md): estado, ownership y operacion del proyecto
- [ADRs.md](ADRs.md): decisiones arquitectonicas congeladas
- [DEPLOYMENT.md](DEPLOYMENT.md): despliegue a produccion
- [START_LOCAL.md](START_LOCAL.md): quick-start operativo local
- OpenAPI Swagger: documentacion auto-generada del backend

## Historial de entregas

- `3734b76` - Feat: DB schema + ORM models (via Claude) - Task #1
- `f9ffb79` - Feat: LiteLLM router + model abstraction (via Claude) - Task #2
- `04aab94` - Feat: Task executor + context manager (via Claude) - Task #3
- `f273c1a` - Feat: Evaluation framework + multi-layer checks (via Codex) - Task #4
- `9cd1ac4` - Feat: React dashboard (via Gemini) - Task #5
- `649a6b3` - Feat: Tests + CI/CD pipeline (via Codex) - Task #6
- `004001c` - Test: E2E validation of SmartRouter with real ticket (full paralelization flow)

## Que puede hacer una empresa con esto hoy

- crear tickets y tasks en BD
- ejecutar tareas con un click o por API
- monitorizar evaluaciones en tiempo real
- revertir fallos automaticamente
- inspeccionar logs de cada agente
- usar la plataforma como base de una operacion de ingenieria asistida por IA

## Proximos pasos

### v0.2

- intake automatizado desde ticket real
- CRUD completo de tickets
- dashboard mas potente
- integracion con CRM / Jira / Linear
- mas pruebas end-to-end

### v1.0

- pipeline multi-agente autonomo
- politicas de evaluacion configurables
- observabilidad avanzada
- despliegue productivo con alertas
- optimizacion de coste y rendimiento por agente

## Mensaje final

ADP no es un experimento aislado. Es el inicio de una plataforma que convierte la ingenieria de software en una operacion automatizada, auditable y escalable. Lee tickets, asigna trabajo, genera artefactos, valida resultados, documenta el contexto y se recupera cuando algo falla.

En otras palabras: una empresa puede empezar a usar ADP para transformar backlog en entregas validadas, con menos coste operativo, mas velocidad y mayor control.
