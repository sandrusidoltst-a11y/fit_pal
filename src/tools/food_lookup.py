from langchain_core.tools import tool

@tool
def lookup_food(query: str) -> str:
    """
    Look up nutritional information for a food item.
    
    Args:
        query: The food item to search for (e.g., "chicken breast", "apple").
        
    Returns:
        JSON string containing nutritional info (calories, protein, carbs, fat).
    """
    # Placeholder logic until DB is integrated
    return f"Mock data for {query}: 100 kcal, 10g protein"
