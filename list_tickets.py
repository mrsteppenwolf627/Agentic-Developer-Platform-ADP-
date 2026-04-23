import psycopg2

conn = psycopg2.connect('postgresql://postgres.ftzxurbxqqaxcmgsbtbv:!w2~4SB8x%5Eks@aws-1-eu-west-3.pooler.supabase.com:5432/postgres')
cursor = conn.cursor()

# Buscar TODOS los tickets (últimos 5)
cursor.execute("SELECT id, title FROM tickets ORDER BY created_at DESC LIMIT 5")
tickets = cursor.fetchall()

print("✅ ÚLTIMOS 5 TICKETS EN LA BD:")
for ticket in tickets:
    print(f"   ID: {ticket[0]}")
    print(f"   Título: {ticket[1]}")
    print()

cursor.close()
conn.close()
