import psycopg2

conn = psycopg2.connect('postgresql://postgres.ftzxurbxqqaxcmgsbtbv:!w2~4SB8x%5Eks@aws-1-eu-west-3.pooler.supabase.com:5432/postgres')
cursor = conn.cursor()

# Buscar el ticket
ticket_id = '88c61422-84ed-44d0-bfb6-edc98aef8003'

cursor.execute("SELECT id, title, status FROM tickets WHERE id = %s", (ticket_id,))
ticket = cursor.fetchone()

if ticket:
    print(f"✅ TICKET ENCONTRADO:")
    print(f"   ID: {ticket[0]}")
    print(f"   Título: {ticket[1]}")
    print(f"   Status: {ticket[2]}")
    print()
    
    # Buscar tasks del ticket
    cursor.execute("SELECT id, name, status FROM tasks WHERE ticket_id = %s", (ticket_id,))
    tasks = cursor.fetchall()
    
    if tasks:
        print(f"✅ TASKS ENCONTRADAS ({len(tasks)}):")
        for task in tasks:
            print(f"   - {task[1]} (id: {task[0][:8]}..., status: {task[2]})")
    else:
        print(f"❌ NO HAY TASKS para este ticket")
else:
    print(f"❌ TICKET NO ENCONTRADO")

cursor.close()
conn.close()
