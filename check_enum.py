import psycopg2

conn = psycopg2.connect('postgresql://postgres.ftzxurbxqqaxcmgsbtbv:!w2~4SB8x%5Eks@aws-1-eu-west-3.pooler.supabase.com:5432/postgres')
cursor = conn.cursor()

# Ver los valores permitidos de enums
cursor.execute("""
    SELECT enumlabel 
    FROM pg_enum 
    WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'ticket_priority')
    ORDER BY enumsortorder;
""")

priorities = cursor.fetchall()
print("✅ Valores válidos para 'priority':")
for p in priorities:
    print(f"  - {p[0]}")

cursor.close()
conn.close()
