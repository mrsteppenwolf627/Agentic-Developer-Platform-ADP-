import psycopg2
import uuid
from datetime import datetime

conn = psycopg2.connect('postgresql://postgres.ftzxurbxqqaxcmgsbtbv:!w2~4SB8x%5Eks@aws-1-eu-west-3.pooler.supabase.com:5432/postgres')
cursor = conn.cursor()

# Crear un nuevo ticket
ticket_id = str(uuid.uuid4())
now = datetime.utcnow().isoformat() + 'Z'

cursor.execute("""
    INSERT INTO tickets (id, title, description, status, priority, required_models, context_snapshot, created_at, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
""", (
    ticket_id,
    'E2E Test: Build user dashboard with filters',
    'Create a React dashboard with user list, advanced filters, pagination, and API integration with backend validation. This includes: 1) Frontend component (React), 2) Backend logic (filters, pagination), 3) Database queries, 4) Integration tests',
    'pending',
    'P0',
    '["claude", "gemini", "codex"]',
    '{}',
    now,
    now
))

conn.commit()
print(f"✅ TICKET CREADO EXITOSAMENTE")
print(f"📌 Ticket ID: {ticket_id}")

cursor.close()
conn.close()
