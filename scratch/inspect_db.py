
import sqlite3
try:
    conn = sqlite3.connect('clipmind_dev.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, email FROM users LIMIT 1;")
    row = cursor.fetchone()
    print(f"User Row: {row}")
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"Tables: {[t[0] for t in tables]}")
    
    conn.close()
except Exception as e:
    print(f"Error: {e}")
