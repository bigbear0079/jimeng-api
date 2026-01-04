import sqlite3

conn = sqlite3.connect('data.db')
cursor = conn.cursor()

# 查看所有表
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables:", tables)

# 查看账户数据
for table in tables:
    table_name = table[0]
    print(f"\n--- {table_name} ---")
    cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
    rows = cursor.fetchall()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    print("Columns:", columns)
    print("Sample data:", rows[:2] if rows else "Empty")
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    print("Total rows:", cursor.fetchone()[0])

conn.close()
