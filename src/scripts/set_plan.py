"""
Coach CLI script: set a nutrition plan for a user.

Usage:
    uv run python src/scripts/set_plan.py <user_id> <plan_file.txt>

Example:
    uv run python src/scripts/set_plan.py fbeeb45f-d728-4c7c-9e6d-7b9b41685da7 plans/brother_plan.txt
"""
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

from src.database import get_async_db_session  # noqa: E402
from src.services.user_profile_service import set_nutrition_plan  # noqa: E402


async def main(user_id: str, plan_file: str) -> None:
    with open(plan_file, "r", encoding="utf-8") as f:
        plan_text = f.read()

    async with get_async_db_session() as session:
        await set_nutrition_plan(session, user_id, plan_text)
        print(f"Plan updated for user {user_id} ({len(plan_text)} chars)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: uv run python src/scripts/set_plan.py <user_id> <plan_file>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
