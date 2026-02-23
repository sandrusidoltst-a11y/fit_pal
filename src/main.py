import asyncio
import sys
import os

# Add the src directory to the python path to ensure imports work correctly
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.agents.nutritionist import define_graph

async def main():
    print("Initializing FitPal Agent...")
    try:
        await define_graph()
        print("Graph compiled successfully.")
        print("FitPal Agent is ready.")
    except Exception as e:
        print(f"Error initializing agent: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
