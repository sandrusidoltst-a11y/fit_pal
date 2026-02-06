import csv
import os
import sys

# Add the project root to the python path to allow imports from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.database import get_db_session, engine
from src.models import Base, FoodItem
from src.config import BASE_DIR

CSV_PATH = os.path.join(BASE_DIR, "data", "nutrients_csvfile.csv")

def clean_val(val):
    """Cleans numeric values from CSV (handles 't', 'a', commas)."""
    if not val:
        return 0.0
    val = val.strip().lower()
    if val in ['t', 'a']: # Trace amounts or other non-numeric markers found in this specific CSV
        return 0.0
    val = val.replace(',', '')
    try:
        return float(val)
    except ValueError:
        return 0.0

def ingest_data():
    print(f"Reading CSV from: {CSV_PATH}")
    
    session = get_db_session()
    
    # Reset Database
    print("Resetting database...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    items_to_add = []
    
    with open(CSV_PATH, mode='r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        
        for row in reader:
            name = row.get("Food")
            measure = row.get("Measure")
            grams_str = row.get("Grams")
            calories_str = row.get("Calories")
            protein_str = row.get("Protein")
            fat_str = row.get("Fat")
            carbs_str = row.get("Carbohydrates") # Column name in CSV is "Carbohydrates" or "Carbs"? Checking file view... it was "Carbs" on line 1?
            # Re-checking View File output for CSV header: "Food,Measure,Grams,Calories,Protein,Fat,Sat.Fat,Fiber,Carbs,Category"
            carbs_str = row.get("Carbs")
            
            if not name or not grams_str:
                continue
                
            grams = clean_val(grams_str)
            if grams == 0:
                print(f"Skipping {name} due to 0 grams.")
                continue
            
            calories = clean_val(calories_str)
            protein = clean_val(protein_str)
            fat = clean_val(fat_str)
            carbs = clean_val(carbs_str)
            category = row.get("Category")

            # Handle ambiguous names by prepending category (requested by user)
            # Specifically for "Breads, cereals, fastfood,grains" which has entries like "White, 20 slices"
            if category and "Breads" in category:
                # Prepend the category to make the name unique and descriptive
                # e.g. "Breads, cereals, fastfood,grains - White, 20 slices"
                # Consolidate the long category name for readability if preferred, 
                # but user asked for "bread category details".
                name = f"{category} - {name}"
            
            # Normalize to 100g
            # Formula: (val / grams) * 100
            norm_calories = (calories / grams) * 100
            norm_protein = (protein / grams) * 100
            norm_fat = (fat / grams) * 100
            norm_carbs = (carbs / grams) * 100
            
            food_item = FoodItem(
                name=name,
                calories=round(norm_calories, 2),
                protein=round(norm_protein, 2),
                fat=round(norm_fat, 2),
                carbs=round(norm_carbs, 2)
            )
            items_to_add.append(food_item)

    print(f"Adding {len(items_to_add)} items to database...")
    session.add_all(items_to_add)
    session.commit()
    session.close()
    print("Ingestion complete!")

if __name__ == "__main__":
    ingest_data()
