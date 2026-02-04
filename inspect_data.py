import pandas as pd

file_path = 'data/MyFoodData-Nutrition-Facts-SpreadSheet-Release-1-4.xlsx'

try:
    print(f"Reading {file_path}...")
    # Read first 10 rows to scan for headers
    df_raw = pd.read_excel(file_path, header=None, nrows=10)
    
    header_idx = -1
    for idx, row in df_raw.iterrows():
        # Check if row looks like it has headers
        row_str = " ".join(str(x) for x in row.values).lower()
        if "protein" in row_str and "fat" in row_str:
            header_idx = idx
            print(f"Found potential header at row {idx}")
            print(row.values)
            break
            
    if header_idx != -1:
        # Reload with correct header
        df = pd.read_excel(file_path, header=header_idx, nrows=5)
        print("\n--- Columns found ---")
        for col in df.columns:
            if any(k in str(col).lower() for k in ['name', 'cal', 'prot', 'fat', 'carb', 'id']):
                print(f"- {col}")
        
        print("\n--- Sample Data ---")
        item_col = [c for c in df.columns if "name" in str(c).lower()][0]
        cal_col = [c for c in df.columns if "cal" in str(c).lower()][0]
        print(df[[item_col, cal_col]].head(3).to_string())

    else:
        print("Could not find a header row with Protein/Fat.")
        print(df_raw.head(5).to_string())

except Exception as e:
    print(f"Error: {e}")
