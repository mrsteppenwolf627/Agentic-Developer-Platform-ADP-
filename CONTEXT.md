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

---

## ULTIMA ACTUALIZACION

- **Fecha:** 2026-04-21 09:52 (Task #11 completada - documentacion sincronizada para el equipo)
- **Por:** Codex (GPT-5)
- **Cambios:** `README.md` y `CONTEXT.md` sincronizados con el estado real del proyecto para que otros agentes no reutilicen el UUID truncado del ticket; documentado el ticket validado `0e75d3af-40f3-4f03-93df-eeff72903487`, el comando `pytest tests/test_e2e_smart_router_real_ticket.py -v -s`, el comportamiento esperado de SmartRouter (3 componentes paralelos + `Tests` secuencial + `Backend API` critico) y la nota operativa de exportar `DATABASE_URL` porque `app.database` lee `os.environ` directamente
- **Archivos creados:** Ninguno
- **Archivos modificados:** README.md, CONTEXT.md
- **Supabase URL:** https://ftzxurbxqqaxcmgsbtbv.supabase.co
- **GitHub repo:** https://github.com/mrsteppenwolf627/Agentic-Developer-Platform-ADP-.git
