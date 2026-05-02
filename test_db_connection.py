import os
from dotenv import load_dotenv
import psycopg2

# Load .env
load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

try:
    # Connect to Postgres
    conn = psycopg2.connect(
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        sslmode='require'  # Ensure SSL
    )
    print("✅ Connection successful!")
    conn.close()
except Exception as e:
    print("❌ Connection failed:", e)