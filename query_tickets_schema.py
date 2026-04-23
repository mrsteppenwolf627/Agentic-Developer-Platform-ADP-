import psycopg2

conn = psycopg2.connect('postgresql://postgres.ftzxurbxqqaxcmgsbtbv:!w2~4SB8x%5Eks@aws-1-eu-west-3.pooler.supabase.com:5432/postgres')
cursor = conn.cursor()

cursor.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'tickets'
    ORDER BY ordinal_position;
""")

columns = cursor.fetchall()
print("📋 ESTRUCTURA DE TABLA 'tickets':")
for col_name, col_type in columns:
    print(f"  - {col_name}: {col_type}")

cursor.close()
conn.close()
