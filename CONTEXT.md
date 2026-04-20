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

---

## ULTIMA ACTUALIZACION

- **Fecha:** 2026-04-20 14:02 (Task #9 completada - SmartRouter integrado en TaskExecutor)
- **Por:** Codex (GPT-5)
- **Cambios:** TaskExecutor refactorizado en `_load_and_validate_task()` + `_execute_task_internal()`; nuevo `execute_ticket_with_smart_routing()` con analisis SmartRouter, seleccion de modo A/B, aprobacion solo de la wave critica y ejecucion por `asyncio.gather()` usando sesiones aisladas por task; nuevo `ExecutionReport`; nueva suite `tests/test_task_executor_smart_routing.py`; fixture de contexto de tests ajustado para evitar fallo de `tmp_path` en Windows; 8 tests de executor/smart routing en verde
- **Archivos creados:** tests/test_task_executor_smart_routing.py
- **Archivos modificados:** app/services/task_executor.py, tests/conftest.py, CONTEXT.md
- **Supabase URL:** https://ftzxurbxqqaxcmgsbtbv.supabase.co
- **GitHub repo:** https://github.com/mrsteppenwolf627/Agentic-Developer-Platform-ADP-.git
