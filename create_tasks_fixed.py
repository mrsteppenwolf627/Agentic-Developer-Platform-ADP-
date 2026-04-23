import psycopg2
import uuid
from datetime import datetime

conn = psycopg2.connect('postgresql://postgres.ftzxurbxqqaxcmgsbtbv:!w2~4SB8x%5Eks@aws-1-eu-west-3.pooler.supabase.com:5432/postgres')
cursor = conn.cursor()

# El ticket ID correcto (ya existe en la BD)
ticket_id = '0e75d3af-40f3-4f03-93df-eeff7290348'
now = datetime.utcnow().isoformat() + 'Z'

# Crear 4 tasks
task_ids = []

tasks_data = [
    ('Frontend: Build React Dashboard', 'gemini'),
    ('Backend: Implement Filters & Pagination', 'claude'),
    ('Database: Optimize Queries', 'claude'),
]

# Crear tasks 1-3 (sin dependencias)
for task_name, model in tasks_data:
    task_id = str(uuid.uuid4())
    task_ids.append(task_id)
    
    cursor.execute("""
        INSERT INTO tasks (id, ticket_id, name, assigned_model, status, dependencies, created_at, updated_at)
        VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s)
    """, (
        task_id,
        ticket_id,
        task_name,
        model,
        'pending',
        '[]',
        now,
        now
    ))
    print(f"✅ Task creada: {task_name}")
    print(f"   ID: {task_id}")

# Crear task 4 (Tests) con dependencias
task_id_tests = str(uuid.uuid4())
deps_json = str(task_ids).replace("'", '"')

cursor.execute("""
    INSERT INTO tasks (id, ticket_id, name, assigned_model, status, dependencies, created_at, updated_at)
    VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s)
""", (
    task_id_tests,
    ticket_id,
    'Tests: Integration Testing',
    'codex',
    'pending',
    deps_json,
    now,
    now
))
print(f"✅ Task creada: Tests (depende de las 3 anteriores)")
print(f"   ID: {task_id_tests}")

conn.commit()
print(f"\n✅ TODAS LAS TASKS CREADAS")
print(f"   - 3 tasks paralelos")
print(f"   - 1 task secuencial (Tests)")

cursor.close()
conn.close()
