import psycopg2
import uuid
from datetime import datetime

conn = psycopg2.connect('postgresql://postgres.ftzxurbxqqaxcmgsbtbv:!w2~4SB8x%5Eks@aws-1-eu-west-3.pooler.supabase.com:5432/postgres')
cursor = conn.cursor()

ticket_id = '0e75d3af-40f3-4f03-93df-eeff7290348'
now = datetime.utcnow().isoformat() + 'Z'

# Definir las 4 tasks
tasks_data = [
    {
        'name': 'Frontend: Build React Dashboard',
        'assigned_model': 'gemini',
        'dependencies': []
    },
    {
        'name': 'Backend: Implement Filters & Pagination',
        'assigned_model': 'claude',
        'dependencies': []
    },
    {
        'name': 'Database: Optimize Queries',
        'assigned_model': 'claude',
        'dependencies': []
    },
    {
        'name': 'Tests: Integration Testing',
        'assigned_model': 'codex',
        'dependencies': []  # Será actualizado después
    }
]

# Guardar IDs para crear dependencias
task_ids = []

# Crear tasks 1-3 (sin dependencias)
for i, task_data in enumerate(tasks_data[:3]):
    task_id = str(uuid.uuid4())
    task_ids.append(task_id)
    
    cursor.execute("""
        INSERT INTO tasks (id, ticket_id, name, assigned_model, status, dependencies, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        task_id,
        ticket_id,
        task_data['name'],
        task_data['assigned_model'],
        'pending',
        '[]',  # Sin dependencias
        now,
        now
    ))
    print(f"✅ Task {i+1} creada: {task_data['name']}")
    print(f"   ID: {task_id}")

# Crear task 4 (Tests) con dependencias de tasks 1-3
task_id_tests = str(uuid.uuid4())
dependencies_json = str(task_ids).replace("'", '"')  # Convertir a JSON

cursor.execute("""
    INSERT INTO tasks (id, ticket_id, name, assigned_model, status, dependencies, created_at, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
""", (
    task_id_tests,
    ticket_id,
    'Tests: Integration Testing',
    'codex',
    'pending',
    dependencies_json,
    now,
    now
))
print(f"✅ Task 4 creada: Tests (depende de tasks 1-3)")
print(f"   ID: {task_id_tests}")

conn.commit()
print(f"\n✅ TODAS LAS TASKS CREADAS EXITOSAMENTE")
print(f"\nResumen:")
print(f"  - 3 tasks paralelos (Frontend, Backend, Database)")
print(f"  - 1 task secuencial (Tests depende de los 3)")
print(f"  - Ticket ID: {ticket_id}")

cursor.close()
conn.close()
