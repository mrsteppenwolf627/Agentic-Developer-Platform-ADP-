# CONTEXT: Technical Factory — AI-Powered SDLC Automation

**Versión:** 1.0  
**Iniciado:** 2026-04-16 09:00  
**Plazo:** 6 horas (deployment v0.1 a las 15:00)

---

## 🏗️ ARQUITECTURA GENERAL

**Visión:** Sistema multi-agente orquestado que toma tickets (CRM/Backlog) → descompone en tasks → ejecuta con agentes especializados (Gemini/Claude/Codex) → valida con framework de gobernanza → entrega código validado.

**Stack Agnóstico:**
- Orquestación: FastAPI + LiteLLM
- BD Central: Supabase (PostgreSQL)
- Evaluación: Braintrust + Codex
- Agentes: Gemini (UI), Claude (Backend), Codex (Security/Tests)
- Rollback: Snapshots automáticos
- Frontend: React SPA (dashboard mínimo)

---

## 📊 ESTADO ACTUAL

| # | Component | Status | Owner | Notes |
|---|---|---|---|---|
| 1 | Database Schema | ✅ DONE | Claude | alembic/versions/001 + app/models/ |
| 2 | LiteLLM Router | ⏳ PENDING | Claude | Agnóstico de modelo |
| 3 | Evaluation Framework | ⏳ PENDING | Codex | Multi-layer evals |
| 4 | Task Executor | ⏳ PENDING | Claude | Orquestación agentes |
| 5 | React Dashboard | ⏳ PENDING | Gemini | Mínimo viable |
| 6 | Tests + Deployment | ⏳ PENDING | Codex | CI/CD |

---

## 🎯 BACKLOG PRIORIZADO (6 horas)

| Tarea | Tiempo Est. | Asignación | Bloques | Prioridad |
|---|:---:|:---:|:---:|:---:|
| DB Schema + Migrations | 30min | Claude | — | 🔴 P0 |
| LiteLLM Router Setup | 45min | Claude | DB | 🔴 P0 |
| Task Executor (orquestación) | 60min | Claude | LiteLLM | 🔴 P0 |
| Evaluation Framework | 45min | Codex | Executor | 🔴 P0 |
| React Dashboard (basic) | 45min | Gemini | Executor | 🟠 P1 |
| Tests + GitHub Actions | 30min | Codex | Todo | 🟠 P1 |
| Documentation + Deploy | 15min | Cualquiera | Todo | 🟠 P1 |

**Total estimado: 250min ≈ 4h 10min** (margen: 1h 50min para debugging/iteración)

---

## 🔐 RESTRICCIONES CRÍTICAS

- **Plazo:** 6 horas hard stop (15:00 UTC)
- **Testing:** Mín 70% coverage (MVP)
- **Seguridad:** Evaluación obligatoria en TODOS los outputs
- **Compliance:** GDPR readiness (encriptación en tránsito)
- **Zero manual deployments:** CI/CD automatizado

---

## 🔄 CONVENCIONES GIT
Commits: git commit -m "Feat: [desc] (via Claude/Gemini/Codex) - Task #X"
Branches: feature/task-{id}, fix/bug-{id}
PR required: True (si no es trivial)

---

## 📍 NOTAS OPERATIVAS

- **Validación OBLIGATORIA** antes de sobrescribir CONTEXT.md
- **Snapshots automáticos** en rollback_stack antes de cada task
- **Consultar ADRs.md** antes de decisiones arquitectónicas
- **Logging centralizado** en agent_sessions para auditoría
- **No partial states:** Si algo falla, rollback inmediato

---

## 🔗 REFERENCIAS

- **ADRs.md:** Decisiones congeladas (ADR-001, ADR-002, ADR-003)
- **Diseño de Datos:** [Ver sección arriba]
- **Royal Roads:** [Ver patrones de integración]

---

## 📋 TAREAS EJECUTADAS HOY

(Este log se actualiza después de cada tarea exitosa)

- [x] **Task #1:** DB Schema → Completada por Claude (claude-sonnet-4-6) @ 2026-04-16 ~09:30
- [ ] **Task #2:** LiteLLM Router → Completada por [modelo] @ [hora]
- [ ] **Task #3:** Task Executor → Completada por [modelo] @ [hora]
- [ ] **Task #4:** Evaluation Framework → Completada por [modelo] @ [hora]
- [ ] **Task #5:** React Dashboard → Completada por [modelo] @ [hora]
- [ ] **Task #6:** Tests + Deploy → Completada por [modelo] @ [hora]

---

## 🔐 ÚLTIMA ACTUALIZACIÓN

- **Fecha:** 2026-04-16 09:30 (Task #1 completada)
- **Por:** Claude (claude-sonnet-4-6)
- **Cambios:** DB Schema + Alembic migrations + ORM models + Pydantic schemas
- **Archivos creados:** ADRs.md, alembic.ini, alembic/env.py, alembic/versions/001_initial_schema.py, app/models/schemas.py, app/models/__init__.py, app/database.py, .env.example
- **Supabase URL:** https://ftzxurbxqqaxcmgsbtbv.supabase.co
- **GitHub repo:** https://github.com/mrsteppenwolf627/Agentic-Developer-Platform-ADP-.git