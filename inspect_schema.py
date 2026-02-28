import sqlite3

try:
    conn = sqlite3.connect('data/nutrition.db')
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(food_items)")
    columns = cursor.fetchall()
    print("Columns:", columns)
    
    cursor.execute("SELECT rowid, * FROM food_items LIMIT 1")
    row = cursor.fetchone()
    print("First row with rowid:", row)
    conn.close()
except Exception as e:
    print(e)
