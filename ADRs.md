# ADRs — Architectural Decision Records
# Technical Factory — AI-Powered SDLC Automation

**Formato:** ADR-XXX | Título | Estado | Fecha  
**Estados:** proposed → accepted | deprecated | superseded

---

## ADR-001: Stack de Persistencia — PostgreSQL via Supabase

**Estado:** accepted  
**Fecha:** 2026-04-16  
**Aprobado por:** Arquitecto de Sistemas  
**Impact area:** database, data-model, migrations

### Contexto
El sistema necesita persistir tickets, tasks, evaluations, sessions y snapshots de contexto. Los datos son semi-estructurados (JSONB para logs/findings), contienen arrays de UUIDs (dependencies), y requieren búsquedas frecuentes por status y FK.

### Decisión
- **Base de datos:** PostgreSQL (vía Supabase) como única fuente de verdad
- **ORM:** SQLAlchemy 2.0 (estilo `Mapped[]` + `mapped_column`)
- **Migraciones:** Alembic con auto-generate
- **Driver async:** `asyncpg` para la app, `psycopg2` para migraciones Alembic
- **Tipos nativos usados:** `UUID`, `JSONB`, `ARRAY`, `ENUM`, `TIMESTAMPTZ`

### Consecuencias
- (+) JSONB soporta búsquedas indexadas en `findings` y `context_snapshot`
- (+) ARRAY(UUID) para `dependencies` sin tabla join extra
- (+) Supabase provee auth, realtime y storage out-of-the-box
- (-) No portable a SQLite para tests locales sin mocks
- **Mitigación:** Usar `testcontainers-python` con PostgreSQL real en CI

### Restricciones congeladas
- NO usar SQLite en ningún entorno
- Todas las PKs deben ser `UUID` generado por `gen_random_uuid()`
- Excepción: `adrs.id` es `INT` por convención de numeración ADR

---

## ADR-002: Asignación de Modelos por Especialidad (via LiteLLM)

**Estado:** accepted  
**Fecha:** 2026-04-16  
**Aprobado por:** Arquitecto de Sistemas  
**Impact area:** agent-routing, task-execution, litellm-config

### Contexto
El sistema orquesta múltiples modelos LLM. Cada modelo tiene fortalezas distintas. Se necesita routing determinístico basado en el tipo de tarea para maximizar calidad y minimizar costos.

### Decisión
| Modelo | Rol | Tareas asignadas |
|--------|-----|-----------------|
| `claude` | Backend Architect | APIs, lógica de negocio, BD, orquestación |
| `gemini` | UI/UX Specialist | Frontend React, componentes, estilos |
| `codex` | Security + QA | Tests, security review, compliance |
| `braintrust` | Evaluador externo | Scoring de calidad de outputs |

**Router:** LiteLLM como proxy agnóstico. Config en `litellm_config.yaml`.  
**Fallback:** Si modelo principal falla → retry con modelo secundario (máx 2 intentos).  
**ENUM en BD:** `agent_model = {gemini, claude, codex}` para tasks/sessions.

### Consecuencias
- (+) Cada modelo se usa donde tiene ventaja comparativa
- (+) LiteLLM permite cambiar proveedor sin modificar código
- (-) Dependencia en 3 APIs externas simultáneas
- **Mitigación:** `agent_sessions` registra latencia y tokens por sesión para optimizar

### Restricciones congeladas
- NO hardcodear API keys en código → usar `.env` + `os.getenv()`
- El campo `assigned_model` en `tasks` es INMUTABLE una vez asignado
- Toda ejecución de modelo DEBE crear un registro en `agent_sessions`

---

## ADR-003: Framework de Evaluación Multi-Capa (Mandatory Gate)

**Estado:** accepted  
**Fecha:** 2026-04-16  
**Aprobado por:** Arquitecto de Sistemas  
**Impact area:** evaluations, governance, task-lifecycle

### Contexto
El sistema genera código automáticamente. Sin evaluación obligatoria, outputs inseguros o de baja calidad podrían mergearse a producción. Se requiere un sistema de gobernanza que bloquee avance si el output no cumple umbrales mínimos.

### Decisión
**Evaluación obligatoria ANTES de marcar cualquier task como `completed`.**

**Capas de evaluación:**
| Tipo | Evaluador | Score mínimo | Bloquea si falla |
|------|-----------|:------------:|:----------------:|
| `security` | codex | 0.85 | ✅ Sí |
| `quality` | claude | 0.75 | ✅ Sí |
| `functional` | claude | 0.80 | ✅ Sí |
| `compliance` | codex | 0.80 | ✅ Sí |
| `performance` | braintrust | 0.70 | ❌ No (warning) |

**Flujo de evaluación:**
```
task output → evaluación security → evaluación quality → evaluación functional
     ↓ falla cualquiera                    ↓ todas pasan
rollback_stack.state = 'active'    task.status = 'completed'
task.status = 'failed'
```

**Estructura de `findings` JSONB:**
```json
{
  "issues": [{"severity": "high", "description": "...", "line": 42}],
  "recommendations": ["..."],
  "raw_output": "..."
}
```

### Consecuencias
- (+) Zero-trust en outputs de agentes
- (+) Auditoría completa en tabla `evaluations`
- (+) `rollback_stack` permite recovery automático
- (-) Añade latencia (~5-10s por evaluación)
- **Mitigación:** Evaluaciones en paralelo donde no hay dependencia de datos

### Restricciones congeladas
- `passed = false` en evaluación de seguridad → rollback INMEDIATO
- Score en rango `[0.0, 1.0]` float, NO porcentaje
- `evaluated_by` DEBE coincidir con el evaluador real que generó el score
- NUNCA marcar `task.status = 'completed'` sin evaluación previa registrada
