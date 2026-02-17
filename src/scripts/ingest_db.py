import os
import sqlite3
import pandas as pd

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
EXCEL_PATH = os.path.join(DATA_DIR, "MyFoodData-Nutrition-Facts-SpreadSheet-Release-1-4.xlsx")
DB_PATH = os.path.join(DATA_DIR, "nutrition.db")

def ingest_data():
    print(f"Loading Excel file from: {EXCEL_PATH}")
    
    # We found in inspection that:
    # Key columns are: 'name', 'Calories', 'Protein (g)', 'Fat (g)', 'Carbohydrate (g)'
    # We need to find the header row first as we did in inspection
    
    try:
        # 1. Read Excel to find header
        df_raw = pd.read_excel(EXCEL_PATH, header=None, nrows=10)
        header_idx = -1
        for idx, row in df_raw.iterrows():
            row_str = " ".join(str(x) for x in row.values).lower()
            if "protein" in row_str and "fat" in row_str:
                header_idx = idx
                break
        
        if header_idx == -1:
            raise ValueError("Could not detect header row with 'Protein' and 'Fat' columns.")
            
        print(f"Detected header at row {header_idx}. Reading full dataset...")
        
        # 2. Read full dataset with correct header
        df = pd.read_excel(EXCEL_PATH, header=header_idx)
        
        # 3. Rename columns to our internal schema
        # Map: Excel Column -> SQL Column
        # Note: We need to handle potential whitespace or exact naming
        col_map = {}
        for col in df.columns:
            c_str = str(col).strip()
            if c_str.lower() == "name":
                col_map[col] = "name"
            elif "calories" in c_str.lower() and "weight" not in c_str.lower(): # Avoid '200 Calorie Weight'
                 col_map[col] = "calories"
            elif "protein (g)" in c_str.lower():
                col_map[col] = "protein"
            elif "fat (g)" in c_str.lower() and "saturated" not in c_str.lower():
                col_map[col] = "fat"
            elif "carbohydrate (g)" in c_str.lower():
                col_map[col] = "carbs"
                
        print(f"Mapped columns: {col_map.values()}")
        
        # Select and Rename
        df_clean = df[list(col_map.keys())].rename(columns=col_map)
        
        # 4. Clean Data
        # Fill NaNs with 0 for macros
        df_clean = df_clean.fillna(0)
        
        # Ensure 'name' is string
        df_clean['name'] = df_clean['name'].astype(str)
        
        # 5. Create SQLite DB
        print(f"Creating database at {DB_PATH}...")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS food_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                calories REAL,
                protein REAL,
                fat REAL,
                carbs REAL
            )
        """)
        
        # Create Index for faster searching on name
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_food_name ON food_items(name)")
        
        # 6. Insert Data
        print(f"Inserting {len(df_clean)} rows...")
        # 6. Insert Data
        print(f"Inserting {len(df_clean)} rows...")
        # Add explicit ID column
        df_clean.insert(0, 'id', range(1, 1 + len(df_clean)))
        
        # Use simple integer for ID in pandas, but specify PK in SQL via dtype if possible, 
        # or just let it be an integer and rely on index. 
        # Better: Write to a temp table or use the dtype dict.
        # from sqlalchemy.types import Integer
        df_clean.to_sql('food_items', conn, if_exists='replace', index=False, dtype={'id': "INTEGER PRIMARY KEY"}) 
        # Note: 'replace' drops the table, so we lose the index if we aren't careful, 
        # but to_sql replace is cleaner for a script. Let's re-add index after.
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_food_name ON food_items(name)")
        
        conn.commit()
        conn.close()
        
        print("Ingestion complete successfully.")
        
    except Exception as e:
        print(f"Error during ingestion: {e}")
        raise

if __name__ == "__main__":
    ingest_data()
