import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def insert_ticket():
    db_url = os.getenv("DATABASE_URL")
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    
    conn = await asyncpg.connect(db_url)
    
    result = await conn.fetchrow("""
        INSERT INTO tickets (title, description, priority, status, created_by)
        VALUES (, , , , )
        RETURNING id, title
    """, 
        "Build login form component",
        "Create React login form with validation",
        "high",
        "open",
        "admin"
    )
    
    print(f"✅ Ticket creado: ID={result['id']}, Title={result['title']}")
    await conn.close()

asyncio.run(insert_ticket())
