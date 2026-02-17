from langchain_core.tools import tool
from sqlalchemy import select
from src.database import get_db_session
from src.models import FoodItem

@tool
def search_food(query: str) -> list[dict]:
    """
    Search for food items by name. 
    Returns a list of candidates with ID and Name only.
    Use this to find the correct food_id before calculating macros.
    """
    session = get_db_session()
    try:
        # Simple ILIKE query
        stmt = select(FoodItem.id, FoodItem.name).where(FoodItem.name.ilike(f"%{query}%")).limit(10)
        results = session.execute(stmt).all()
        return [{"id": r.id, "name": r.name} for r in results]
    finally:
        session.close()

@tool
def calculate_food_macros(food_id: int, amount_g: float) -> dict:
    """
    Calculate nutritional values for a specific food item and amount (in grams).
    Returns dictionary with Name, Calories, Protein, Fat, Carbs.
    """
    session = get_db_session()
    try:
        food = session.get(FoodItem, food_id)
        if not food:
            return {"error": f"Food item with ID {food_id} not found"}
        
        # Calculate ratio
        ratio = amount_g / 100.0
        
        return {
            "name": food.name,
            "amount_g": amount_g,
            "calories": round(food.calories * ratio, 2),
            "protein": round(food.protein * ratio, 2),
            "fat": round(food.fat * ratio, 2),
            "carbs": round(food.carbs * ratio, 2)
        }
    finally:
        session.close()
