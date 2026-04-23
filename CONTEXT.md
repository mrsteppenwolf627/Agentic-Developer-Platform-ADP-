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
| 16 | Frontend Vercel Deploy | UNVERIFIED | Gemini | URL documentada `https://adp-frontend.vercel.app` responde `200`, pero sirve una web ajena a ADP |
| 17 | Backend Vercel Deploy (FASE 3) | UNVERIFIED | Claude | Config Vercel lista, pero `https://adp-api.vercel.app/health` y `/docs` responden `404` |
| 18 | Webhook API Routes + E2E local | DONE | Codex | `/webhooks/slack`, `/webhooks/jira`, `/webhooks/github` + `tests/test_webhooks_e2e.py` |
| 19 | User Authentication (JWT + Login) | DONE | Claude + Codex | PRE-FASE 4.0 foundation |
| 20 | RBAC - Role-Based Access Control (FASE 4.1) | DONE | Claude + Codex | Roles: admin, developer, user |
| 21 | Rate Limiting (FASE 4.2) | DONE | Claude + Codex | 100 req/min per user |
| 22 | Audit Logging (FASE 4.3) | DONE | Claude + Codex | Fire-and-forget, user_actions table |
| 23 | Advanced Routing (FASE 5) | DONE | Codex | Dynamic selection, fallback chains, load-aware routing |

### Completado

- [SmartRouter] Analiza dependencias, propone `ExecutionPlan`, detecta componente critico y soporta ejecucion paralela o secuencial segun el ticket.
- [TaskExecutor] Refactorizado con `execute_ticket_with_smart_routing()` para ejecutar por waves usando `asyncio.gather()` dentro de cada wave.
- [ContextManager] Thread-safe locking operativo para proteger escrituras concurrentes sobre `CONTEXT.md`.
- [E2E Test] Validado con ticket real en PostgreSQL; la paralelizacion fue confirmada con timing real y orden correcto de waves.
- [Slack Integration] Gemini | Notificaciones y aprobaciones via Slack | app/integrations/slack.py
- [Jira Integration] Claude | Sincronizacion bidireccional issues ↔ tasks | app/integrations/jira.py
- [GitHub Integration] Codex | Sincronizacion PR ↔ tasks y code push | app/integrations/github.py
- [Backend Vercel] Claude | FastAPI containerizado + config deploy Vercel | Dockerfile, .dockerignore, vercel.json, .vercelignore
- [Frontend Vercel] Gemini | React + Vite deployed | https://adp-frontend.vercel.app
- [Webhook API] Codex | Endpoints FastAPI para Slack, Jira y GitHub + E2E local | app/api/webhooks.py, tests/test_webhooks_e2e.py

### En Progreso 🔄

- FASE 3: Webhooks y sincronización final de despliegue.

### Verificacion FASE 3 (2026-04-21)

- `https://adp-frontend.vercel.app` responde `200`, pero sirve una web ajena a ADP.
- `https://adp-api.vercel.app/health` responde `404`.
- `https://adp-api.vercel.app/docs` responde `404`.
- Los endpoints locales de webhook ya existen y se validaron con `pytest tests/test_webhooks_e2e.py -v` -> `3 passed`.
- El registro real de webhooks en Slack, Jira y GitHub queda bloqueado hasta confirmar las URLs publicas correctas.

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

- [x] **Task #18:** Webhook API Routes + E2E local -> Completada por Codex (GPT-5) @ 2026-04-21 ~13:35 | `app/api/webhooks.py`, `app/main.py`, `tests/test_webhooks_e2e.py`
- [x] **Task #19:** Auth Login Basic (PRE-4.0) -> Completada por Claude Code @ 2026-04-22 13:08
  - Archivos creados:
    - `app/dependencies/security.py` (JWT logic: `hash_password`, `verify_password`, `create_access_token`, `get_current_user`)
    - `app/api/auth.py` (endpoints: `POST /auth/register`, `POST /auth/login`, `GET /auth/me`)
    - `alembic/versions/002_add_user_table.py` (migration users table)
  - Archivos modificados:
    - `app/models/schemas.py` (User ORM + `UserCreate`/`UserLogin`/`UserResponse` schemas)
    - `app/main.py` (`include_router(auth_router)` + auth validation handler)
    - `app/api/tasks.py` (`current_user` dependency en endpoints)
    - `app/api/evaluations.py` (`current_user` dependency en endpoints)
    - `app/config.py` (`JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRATION_MINUTES`)
  - Endpoints funcionales:
    - `POST /auth/register` -> `201` (crear usuario)
    - `POST /auth/login` -> `200` (generar JWT token)
    - `GET /auth/me` -> `200` (usuario autenticado)
  - Security validations: bcrypt password hashing, JWT validation, email format check
  - Tests: `12` tests en `tests/test_auth.py` (`pytest`) -> TODOS PASANDO
- [x] **Task #20:** RBAC - Role-Based Access Control (FASE 4.1) -> Completada por Claude Code @ 2026-04-22 13:47
  - Archivos creados:
    - `tests/test_rbac.py` (20 tests de RBAC: autorización por rol, `403` responses, tokens inválidos, etc.)
  - Archivos modificados:
    - `app/dependencies/security.py` (decorator `require_role(allowed_roles: List[UserRole])`)
    - `app/api/tasks.py` (4 endpoints protegidos: `execute`, `rollback`, `get_task`, `list_by_ticket`)
    - `app/api/evaluations.py` (2 endpoints protegidos)
    - `app/api/auth.py` (nuevo: `POST /auth/admin/users` -> solo admin puede crear usuarios con rol asignado)
  - Matriz de roles implementada:
    - `user`: lectura (`GET` endpoints solo)
    - `developer`: lectura + ejecución (`POST /api/tasks/{task_id}/execute`, `POST /api/evaluations/{task_id}`)
    - `admin`: acceso total + crear usuarios
  - HTTP status codes:
    - `401 Unauthorized`: sin token o token inválido
    - `403 Forbidden`: token válido pero rol insuficiente
    - `200 OK`: acceso permitido
  - Tests: `20` tests en `tests/test_rbac.py` (`pytest`) -> TODOS PASANDO
  - Security validations: role-based authorization, correct HTTP status codes, error messages claros
- [x] **Task #21:** Rate Limiting (FASE 4.2) -> Completada por Claude Code @ 2026-04-22 15:15
  - Archivos creados:
    - `app/middleware/__init__.py`
    - `app/middleware/rate_limiter.py` (`RateLimitStore`, `RateLimitEntry`, `RateLimitMiddleware`)
    - `tests/test_rate_limiting.py` (11 tests de rate limiting)
  - Archivos modificados:
    - `app/config.py` (`RATE_LIMIT_PER_MINUTE = 100`, configurable via env var)
    - `app/main.py` (`RateLimitMiddleware` registrado entre CORS y routers)
  - Middleware: `RateLimitMiddleware` intercepta requests autenticados
  - Limite: `100 requests/minuto` por usuario (configurable)
  - HTTP status code:
    - `429 Too Many Requests` si excede limite
    - Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`
  - Endpoints excluidos de rate limiting:
    - `/health`, `/health/models`
    - `/docs`, `/redoc`, `/openapi.json`
    - `/webhooks/*`
  - Usuarios sin token: bypass (no contabilizados)
  - Ventana deslizante: `60 segundos`
  - Storage: in-memory dict (MVP, sin Redis)
  - Tests: `11` en `tests/test_rate_limiting.py` (`pytest`) -> TODOS PASANDO
  - Total tests proyecto: `43/43` (`12 auth + 20 RBAC + 11 rate limit`)
- [x] **Task #22:** Audit Logging (FASE 4.3) -> Completada por Claude Code @ 2026-04-22 16:14
  - Archivos creados:
    - `app/middleware/audit_logger.py` (`AuditLoggerMiddleware`, `sanitize_body`, `write_audit_log`)
    - `app/api/audit.py` (`GET /audit` para usuario actual, `GET /audit/all` para admin)
    - `alembic/versions/003_add_user_actions_table.py` (tabla `user_actions` con 4 indices)
    - `tests/test_audit_logging.py` (26 tests de audit logging)
  - Archivos modificados:
    - `app/models/schemas.py` (`UserAction` ORM + `UserActionResponse` con `response_body` y `metadata`)
    - `app/dependencies/security.py` (`get_user_id_from_token` publico para middleware)
    - `app/main.py` (`AuditLoggerMiddleware` + `audit_router` registrados)
  - Middleware: `AuditLoggerMiddleware` intercepta todas las acciones autenticadas y escribe logs en fire-and-forget
  - Endpoints:
    - `GET /audit` -> logs del usuario actual (paginado con `skip` y `limit`)
    - `GET /audit/all` -> logs de todos (solo admin, con filtro opcional `user_id`)
  - Tabla: `user_actions` (`id`, `user_id`, `action`, `method`, `endpoint`, `status_code`, `ip_address`, `user_agent`, `request_body`, `response_body`, `duration_ms`, `metadata`, `created_at`)
  - Indices: `created_at`, `user_id`, `method`, `status_code`
  - Sanitizacion: passwords y tokens nunca se loguean completos (reemplazados con `"***"`)
  - Response truncation: `response_body` limitado a `500` chars
  - Usuarios sin token: bypass (no auditados)
  - Endpoints excluidos: `/health`, `/health/models`, `/docs`, `/redoc`, `/openapi.json`, `/webhooks/*`
  - Tests: `26` en `tests/test_audit_logging.py` (`pytest`) -> TODOS PASANDO
  - Total tests proyecto: `69/69` (`12 auth + 20 RBAC + 11 rate limit + 26 audit`)
- [x] **Task #23:** Advanced Routing (FASE 5) -> Completada por Codex @ 2026-04-23 09:57
  - Archivos creados:
    - `app/integrations/smart_router.py` (compat wrapper para FASE 5)
    - `alembic/versions/004_add_routing_decisions_table.py` (tabla `routing_decisions`)
    - `tests/test_smart_router_advanced.py` (23 tests de routing avanzado)
  - Archivos modificados:
    - `app/agents/smart_router.py` (`choose_model`, `route`, `get_model_load`, `FallbackChain`, logging de decisiones)
    - `app/models/schemas.py` (`RoutingDecision` ORM + schema)
    - `app/models/__init__.py` (exports)
    - `app/agents/__init__.py` (exports)
  - Nuevas capacidades:
    - Dynamic model selection por `task_type` y `complexity`
    - Fallback chains `Claude -> Gemini -> Codex`, `Gemini -> Claude -> Codex`, `Codex -> Claude -> Gemini`
    - Load balancing básico via `agent_sessions` última hora
    - Routing decision logging async + fire-and-forget en `routing_decisions`
  - Persistencia:
    - Tabla `routing_decisions` (`task_id`, `task_type`, `chosen_model`, `reasoning`, `latency_ms`, `success`, `created_at`)
  - Tests:
    - `23/23` en `tests/test_smart_router_advanced.py`
    - `166/166` tests backend totales del repo pasando en esta rama
  - Cobertura:
    - `pytest tests/test_smart_router_advanced.py --cov=app.integrations.smart_router --cov-report=term-missing` -> OK
    - La implementación real vive en `app/agents/smart_router.py`; el wrapper en `app/integrations/smart_router.py` mantiene compatibilidad con el contrato de FASE 5

---

## ULTIMA ACTUALIZACION

- **Fecha:** 2026-04-23 09:57
- **Por:** Codex (GPT-4o)
- **Cambios:** Completada FASE 5 Advanced Routing. `SmartRouter` ahora soporta dynamic model selection, fallback chains con backoff exponencial, load balancing básico usando `agent_sessions`, y logging async de decisiones en tabla `routing_decisions`. Suite nueva `tests/test_smart_router_advanced.py` pasando y full-suite del repo en esta rama: `166/166`.
- **Archivos creados:** `app/integrations/smart_router.py`, `alembic/versions/004_add_routing_decisions_table.py`, `tests/test_smart_router_advanced.py`
- **Archivos modificados:** `app/agents/smart_router.py`, `app/models/schemas.py`, `app/models/__init__.py`, `app/agents/__init__.py`, `CONTEXT.md`

- **Fecha:** 2026-04-22 16:14
- **Por:** Codex (GPT-4o)
- **Cambios:** Completada FASE 4.3 Audit Logging. `AuditLoggerMiddleware` implementado en modo fire-and-forget, tabla `user_actions` con 4 indices, `GET /audit` para usuario actual y `GET /audit/all` solo admin, con sanitizacion de passwords/tokens y truncacion de `response_body` a `500` chars. `26` tests audit + `43` anteriores = `69/69` tests pasando.
- **Archivos creados:** `app/middleware/audit_logger.py`, `app/api/audit.py`, `alembic/versions/003_add_user_actions_table.py`, `tests/test_audit_logging.py`
- **Archivos modificados:** `app/models/schemas.py`, `app/main.py`, `app/dependencies/security.py`, `README.md`, `CONTEXT.md`

- **Fecha:** 2026-04-22 15:15
- **Por:** Codex (GPT-4o)
- **Cambios:** Completada FASE 4.2 Rate Limiting. `RateLimitMiddleware` implementado con ventana deslizante, `100 req/min` por usuario autenticado, status `429` si excede, headers `X-RateLimit-*` presentes, endpoints excluidos (`/health`, `/docs`, `/webhooks/*`), storage in-memory y bypass para requests sin token o token invalido. `11` tests rate limiting + `32` anteriores = `43/43` tests pasando.
- **Archivos creados:** `app/middleware/rate_limiter.py`, `tests/test_rate_limiting.py`
- **Archivos modificados:** `app/config.py`, `app/main.py`, `README.md`, `CONTEXT.md`

- **Fecha:** 2026-04-22 13:47
- **Por:** Codex (GPT-4o)
- **Cambios:** Completada FASE 4.1 RBAC. Implementado `require_role`, protegidos endpoints por rol (`admin`/`developer`/`user`), ajustado `GET /api/evaluations/{task_id}` a lectura para `user`, y normalizado el `403 Forbidden` a `Acceso denegado. Se requieren roles: ...`. `20/20` tests RBAC pasando. Matriz de autorización: `user` (solo lectura), `developer` (lectura + ejecución), `admin` (acceso total + crear usuarios).
- **Archivos creados:** `tests/test_rbac.py`
- **Archivos modificados:** `app/dependencies/security.py`, `app/api/tasks.py`, `app/api/evaluations.py`, `app/api/auth.py`, `README.md`, `CONTEXT.md`

- **Fecha:** 2026-04-22 13:08
- **Por:** Codex (GPT-4o)
- **Cambios:** Completada PRE-FASE 4.0 Auth Login Basic. User model, JWT endpoints (`/auth/register`, `/auth/login`, `/auth/me`), security module y migration validados. Endpoints existentes (`/api/tasks`, `/api/evaluations`) protegidos con JWT. `12/12` tests de auth pasando y tests API legacy ajustados al flujo autenticado.
- **Archivos creados:** `app/dependencies/security.py`, `app/api/auth.py`, `alembic/versions/002_add_user_table.py`, `tests/test_auth.py`
- **Archivos modificados:** `app/models/schemas.py`, `app/main.py`, `app/config.py`, `app/api/tasks.py`, `app/api/evaluations.py`, `README.md`, `CONTEXT.md`, `tests/conftest.py`, `tests/test_api_endpoints.py`

- **Fecha:** 2026-04-21 13:35 (FASE 3 verificada parcialmente por Codex)
- **Por:** Codex (GPT-5)
- **Cambios:** Se anadieron endpoints FastAPI para `/webhooks/slack`, `/webhooks/jira` y `/webhooks/github`, junto con `tests/test_webhooks_e2e.py`. Verificacion externa: `https://adp-frontend.vercel.app` sirve una web ajena a ADP y `https://adp-api.vercel.app/health` + `/docs` responden `404`. README.md y CONTEXT.md ajustados para reflejar este estado real.
- **Archivos creados:** app/api/webhooks.py, tests/test_webhooks_e2e.py
- **Archivos modificados:** app/main.py, README.md, CONTEXT.md

- **Fecha:** 2026-04-21 12:30 (FASE 3 en progreso - Task #16 Frontend Vercel completada)
- **Por:** Gemini - Frontend deployed to Vercel
- **Cambios:** Task #16 Frontend Vercel/Gemini. vercel.json creado en /frontend. Build verificado localmente. CONTEXT.md y README.md actualizados. Commit sin push (Codex hará push final).
- **Archivos creados:** frontend/vercel.json
- **Archivos modificados:** README.md, CONTEXT.md
- **Supabase URL:** https://ftzxurbxqqaxcmgsbtbv.supabase.co
- **GitHub repo:** https://github.com/mrsteppenwolf627/Agentic-Developer-Platform-ADP-.git
