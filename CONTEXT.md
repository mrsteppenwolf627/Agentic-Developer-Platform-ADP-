# CONTEXT: Technical Factory - AI-Powered SDLC Automation

**Version:** 1.0  
**Iniciado:** 2026-04-16 09:00  
**Plazo:** 6 horas (deployment v0.1 a las 15:00)

---

## ARQUITECTURA GENERAL

**Vision:** Sistema multi-agente orquestado que toma tickets (CRM/Backlog) -> descompone en tasks -> ejecuta con agentes especializados (Gemini/Claude/Codex) -> valida con framework de gobernanza -> entrega codigo validado.

**Stack Agnostico:**
- Orquestacion: FastAPI + LiteLLM
- BD Central: Supabase (PostgreSQL)
- Evaluacion: Braintrust + Codex
- Agentes: Gemini (UI), Claude (Backend), Codex (Security/Tests)
- Rollback: Snapshots automaticos
- Frontend: React SPA (dashboard minimo)

---

## ESTADO ACTUAL

| # | Component | Status | Owner | Notes |
|---|---|---|---|---|
| 1 | Database Schema | DONE | Claude | alembic/versions/001 + app/models/ |
| 2 | LiteLLM Router | DONE | Claude | app/agents/ + app/config.py |
| 3 | Evaluation Framework | DONE | Codex | app/services/evaluation_engine.py + app/evaluators/ |
| 4 | Task Executor | DONE | Claude | app/services/ + app/api/tasks.py |
| 5 | React Dashboard | DONE | Gemini | Minimo viable |
| 6 | Tests + Deployment | DONE | Codex | CI/CD + mocks |
| 7 | SmartRouter | DONE | Claude | app/agents/smart_router.py - parallel orchestration |
| 8 | E2E Test SmartRouter con ticket real | DONE | Codex | Ticket 88c61422-84ed-44d0-bfb6-edc98aef8003 validado: 4 componentes, 3 paralelos, 21.8 min, $0.1419 |
| 9 | Integracion SmartRouter en TaskExecutor | DONE | Codex | `execute_ticket_with_smart_routing()`, waves paralelas con sesiones aisladas, HitL sobre wave critica, 8 tests OK |
| 10 | E2E Test SmartRouter con ticket real en PostgreSQL | DONE | Codex | Ticket real `0e75d3af-40f3-4f03-93df-eeff72903487` cargado desde BD, 4 componentes detectados, 3 paralelos, Tests secuencial, Backend API critico, reporte validado en orden, `pytest tests/test_e2e_smart_router_real_ticket.py -v -s` OK |
| 11 | Sync de documentacion operativa | DONE | Codex | `README.md` y `CONTEXT.md` actualizados con ticket real, comando E2E y nota operativa de `DATABASE_URL` |
| 12 | Documentacion FASE 1 completada | DONE | Codex | `README.md` y `CONTEXT.md` sincronizados |
| 13 | Jira Integration (FASE 2) | DONE | Claude | app/integrations/jira.py - sync bidireccional issues ↔ tasks |
| 14 | GitHub Integration (FASE 2) | DONE | Codex | app/integrations/github.py - PR ↔ tasks, code push |
| 15 | Slack Integration (FASE 2) | DONE | Gemini | app/integrations/slack.py - notificaciones y aprobaciones |
| 17 | Backend Vercel Deploy (FASE 3) | DONE | Claude | Dockerfile + vercel.json - FastAPI containerizado y config Vercel lista |

### Completado

- [SmartRouter] Analiza dependencias, propone `ExecutionPlan`, detecta componente critico y soporta ejecucion paralela o secuencial segun el ticket.
- [TaskExecutor] Refactorizado con `execute_ticket_with_smart_routing()` para ejecutar por waves usando `asyncio.gather()` dentro de cada wave.
- [ContextManager] Thread-safe locking operativo para proteger escrituras concurrentes sobre `CONTEXT.md`.
- [E2E Test] Validado con ticket real en PostgreSQL; la paralelizacion fue confirmada con timing real y orden correcto de waves.
- [Slack Integration] Gemini | Notificaciones y aprobaciones via Slack | app/integrations/slack.py
- [Jira Integration] Claude | Sincronizacion bidireccional issues ↔ tasks | app/integrations/jira.py
- [GitHub Integration] Codex | Sincronizacion PR ↔ tasks y code push | app/integrations/github.py
- [Backend Vercel] Claude | FastAPI containerizado + config deploy Vercel | Dockerfile, .dockerignore, vercel.json, .vercelignore

### En Progreso 🔄

- Nada. FASE 2 esta cerrada y validada.

### Pendiente

- FASE 3: Escalabilidad, despliegue en Railway y observabilidad.
- Investigar bug UUID en tabla `tasks` y el uso de IDs truncados en scripts auxiliares / encargos.

### Arquitectura

**Flujo de Decision**

```text
Ticket llega
   |
   v
SmartRouter analiza dependencias
   |
   v
SmartRouter propone ExecutionPlan
   |
   v
Usuario elige:
  A -> Human-in-the-Loop
  B -> Automatizado
   |
   v
TaskExecutor ejecuta por waves
  Wave 1 -> tasks paralelos (asyncio.gather)
     Si HitL -> pide aprobacion de la wave critica
     Ejecuta sin esperar serialmente entre tasks de la wave
  Wave 2 -> tasks secuenciales que dependen de Wave 1
  Wave N -> tareas finales
   |
   v
ContextManager (con lock) actualiza CONTEXT.md
   |
   v
LiteLLM Router elige modelo por task
  Claude / Gemini / Codex + fallback
   |
   v
ExecutionReport
  - Fallos
  - Costo + Tiempo
  - Paralelizacion
  - Sugerencias
```

### Metricas de FASE 1

- Core commits: 3 entregas principales (`SmartRouter`, integracion de `TaskExecutor`, validacion E2E/documentacion).
- Tests: 8 tests de integracion en `tests/test_task_executor_smart_routing.py` + 1 E2E real-ticket en `tests/test_e2e_smart_router_real_ticket.py`.
- Core files touched: 5 areas clave (`app/agents/smart_router.py`, `app/services/task_executor.py`, `app/services/context_manager.py`, `tests/test_task_executor_smart_routing.py`, `tests/test_e2e_smart_router_real_ticket.py`).
- Paralelizacion validada: `asyncio.gather()` con timing real y dependencias respetadas.

### Para El Proximo Developer

- `SmartRouter` es agnostico de modelo; puede convivir con cualquier LLM detras de LiteLLM.
- El sistema soporta tanto paralelo como secuencial; no asumas una DAG totalmente paralela.
- `CONTEXT.md` es la fuente de verdad unica y no debe tratarse como un log descartable.
- El locking thread-safe de `ContextManager` existe para prevenir race conditions en escrituras paralelas.
- LiteLLM router decide modelo; `SmartRouter` decide flujo; `TaskExecutor` materializa la ejecucion.

---

## BACKLOG PRIORIZADO (6 horas)

| Tarea | Tiempo Est. | Asignacion | Bloques | Prioridad |
|---|:---:|:---:|:---:|:---:|
| DB Schema + Migrations | 30min | Claude | - | P0 |
| LiteLLM Router Setup | 45min | Claude | DB | P0 |
| Task Executor (orquestacion) | 60min | Claude | LiteLLM | P0 |
| Evaluation Framework | 45min | Codex | Executor | DONE |
| React Dashboard (basic) | 45min | Gemini | Executor | P1 |
| Tests + GitHub Actions | 30min | Codex | Todo | P1 |
| Documentation + Deploy | 15min | Cualquiera | Todo | P1 |

**Total estimado: 250min ~= 4h 10min** (margen: 1h 50min para debugging/iteracion)

---

## RESTRICCIONES CRITICAS

- **Plazo:** 6 horas hard stop (15:00 UTC)
- **Testing:** Min 70% coverage (MVP)
- **Seguridad:** Evaluacion obligatoria en TODOS los outputs
- **Compliance:** GDPR readiness (encriptacion en transito)
- **Zero manual deployments:** CI/CD automatizado

---

## CONVENCIONES GIT

Commits: `git commit -m "Feat: [desc] (via Claude/Gemini/Codex) - Task #X"`
Branches: `feature/task-{id}`, `fix/bug-{id}`
PR required: True (si no es trivial)

---

## NOTAS OPERATIVAS

- **Validacion OBLIGATORIA** antes de sobrescribir CONTEXT.md
- **Snapshots automaticos** en `rollback_stack` antes de cada task
- **Consultar ADRs.md** antes de decisiones arquitectonicas
- **Logging centralizado** en `agent_sessions` para auditoria
- **No partial states:** Si algo falla, rollback inmediato
- **SmartRouter E2E real:** usar ticket `0e75d3af-40f3-4f03-93df-eeff72903487`; el ID `0e75d3af-40f3-4f03-93df-eeff7290348` estaba truncado en el encargo
- **Runtime DB:** exportar `DATABASE_URL` antes de ejecutar tests o runtime que lean BD real; `app.database` toma la URL desde `os.environ` y si falta cae a `postgresql+asyncpg://postgres:postgres@localhost:5432/adp`

---

## REFERENCIAS

- **ADRs.md:** Decisiones congeladas (ADR-001, ADR-002, ADR-003)
- **Diseno de Datos:** [Ver seccion arriba]
- **Royal Roads:** [Ver patrones de integracion]

---

## TAREAS EJECUTADAS HOY

(Este log se actualiza despues de cada tarea exitosa)

- [x] **Task #1:** DB Schema -> Completada por Claude (claude-sonnet-4-6) @ 2026-04-16 ~09:30
- [x] **Task #2:** LiteLLM Router -> Completada por Claude (claude-sonnet-4-6) @ 2026-04-16 ~10:00
- [x] **Task #3:** Task Executor -> Completada por Claude (claude-sonnet-4-6) @ 2026-04-16 ~10:30
- [x] **Task #4:** Evaluation Framework -> Completada por Codex (GPT-4o) @ 2026-04-16 ~11:55
- [x] **Task #5:** React Dashboard -> Completada por Gemini @ 2026-04-16 ~12:30
- [x] **Task #6:** Tests + Deploy -> Completada por Codex (GPT-4o) @ 2026-04-16 ~13:05
- [x] **Task #7:** SmartRouter - parallel orchestration + file locking -> Completada por Claude (claude-sonnet-4-6) @ 2026-04-20 ~11:50
- [x] **Task #8:** E2E Test SmartRouter con ticket real -> Completada por Codex (GPT-5) @ 2026-04-20 ~13:17
- [x] **Task #9:** Integracion SmartRouter en TaskExecutor -> Completada por Codex (GPT-5) @ 2026-04-20 ~14:02
- [x] **Task #10:** E2E Test SmartRouter con ticket real en PostgreSQL -> Completada por Codex (GPT-5) @ 2026-04-21 ~09:46
- [x] **Task #11:** Sync de documentacion operativa -> Completada por Codex (GPT-5) @ 2026-04-21 ~09:52
- [x] **Task #12:** Documentacion FASE 1 completada -> Completada por Codex (GPT-5) @ 2026-04-21 ~10:00
- [x] **Task #13:** Jira Integration (FASE 2) -> Completada por Claude (claude-sonnet-4-6) @ 2026-04-21 ~10:40 | `app/integrations/jira.py`, `tables/jira_mapping.sql`, `tests/test_jira_integration.py`
- [x] **Task #14:** GitHub Integration (FASE 2) -> Completada por Codex (GPT-5) @ 2026-04-21 ~10:55 | `app/integrations/github.py`, `tables/github_mapping.sql`, `tests/test_github_integration.py`
- [x] **Task #15:** Slack Integration (FASE 2) -> Completada por Gemini @ 2026-04-21 ~11:30 | `app/integrations/slack.py`, `tests/test_slack_integration.py`
- [x] **Task #17:** Backend Vercel Deploy (FASE 3) -> Completada por Claude (claude-sonnet-4-6) @ 2026-04-21 ~12:00 | `Dockerfile`, `.dockerignore`, `vercel.json`, `.vercelignore`, `requirements.txt` (httpx añadido)

---

## ULTIMA ACTUALIZACION

- **Fecha:** 2026-04-21 12:00 (FASE 3 en progreso - Task #17 Backend Vercel completada)
- **Por:** Claude (claude-sonnet-4-6) - containerizacion y config Vercel
- **Cambios:** Task #17 Backend Vercel/Claude. Dockerfile, .dockerignore, vercel.json, .vercelignore creados. httpx añadido a requirements.txt. CONTEXT.md y README.md actualizados con FASE 3 Backend. Commit sin push (Codex hará push final).
- **Archivos creados:** Dockerfile, .dockerignore, vercel.json, .vercelignore
- **Archivos modificados:** requirements.txt, README.md, CONTEXT.md
- **Supabase URL:** https://ftzxurbxqqaxcmgsbtbv.supabase.co
- **GitHub repo:** https://github.com/mrsteppenwolf627/Agentic-Developer-Platform-ADP-.git
