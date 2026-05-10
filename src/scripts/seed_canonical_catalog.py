"""Seed the canonical food catalog into Supabase.

Wipes all `source = 'database'` rows in `food_items` (the legacy ETL seed)
and reseeds from `data/canonical_food_catalog.csv`. For each new food row,
creates a corresponding `coach_food_mappings` row under DEFAULT_COACH_ID.

Run once, after applying the `extend_food_items_and_create_coach_food_mappings`
migration. Estimated user-scoped foods (`source = 'estimated'`) are NOT touched.

Usage:
    uv run python src/scripts/seed_canonical_catalog.py --target supabase
"""

import argparse
import csv
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from src.config import BASE_DIR, DEFAULT_COACH_ID

load_dotenv()

CSV_PATH = os.path.join(BASE_DIR, "data", "canonical_food_catalog.csv")


def _empty_to_none(value):
    """Convert empty string to None; preserve other values."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _to_float(value):
    """Convert string to float, or None if empty."""
    v = _empty_to_none(value)
    return float(v) if v is not None else None


def _clean_str(value):
    """Strip whitespace; treat empty as None."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _to_json_dict(value, default: dict | None = None) -> dict:
    """Parse a JSON-encoded dict from a CSV cell; empty/missing → default ({})."""
    base: dict = {} if default is None else default
    if value is None:
        return dict(base)
    text_value = value.strip() if isinstance(value, str) else value
    if not text_value:
        return dict(base)
    try:
        parsed = json.loads(text_value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in CSV cell: {value!r}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object, got {type(parsed).__name__}: {value!r}")
    return parsed


def parse_csv() -> list[dict]:
    """Parse the canonical food catalog CSV. Returns one dict per row."""
    items = []
    with open(CSV_PATH, mode="r", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            items.append(
                {
                    "name_en": _clean_str(row["name_en"]),
                    "name_he": _clean_str(row["name_he"]),
                    "category": _clean_str(row["category"]),
                    "tag": _clean_str(row["tag"]),
                    "unit_weights": _to_json_dict(row.get("unit_weights")),
                    "unit_synonyms": _to_json_dict(row.get("unit_synonyms")),
                    "serving_amount_g": _to_float(row["serving_amount_g"]),
                    "calories": _to_float(row["calories_per_100g"]),
                    "protein": _to_float(row["protein_per_100g"]),
                    "carbs": _to_float(row["carbs_per_100g"]),
                    "fat": _to_float(row["fat_per_100g"]),
                    "notes": _clean_str(row["notes"]),
                }
            )
    return items


def seed_supabase(items: list[dict]) -> tuple[int, int]:
    """Wipe `database`-source rows and reseed from canonical catalog.

    Returns (food_items_inserted, coach_mappings_inserted).
    """
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        raise ValueError("SUPABASE_DB_URL not set in environment. Add it to .env")

    engine = create_engine(db_url)
    foods_inserted = 0
    mappings_inserted = 0

    with engine.connect() as conn:
        # Wipe in dependency order. CASCADE on coach_food_mappings.food_id handles
        # the FK from coach_food_mappings → food_items, but we explicitly delete
        # any existing mappings for DEFAULT_COACH_ID first to handle script reruns.
        conn.execute(
            text("DELETE FROM coach_food_mappings WHERE coach_id = :coach_id"),
            {"coach_id": str(DEFAULT_COACH_ID)},
        )
        conn.execute(text("DELETE FROM food_items WHERE source = 'database'"))
        conn.commit()

        for item in items:
            # Insert food_items row, capture id.
            food_result = conn.execute(
                text(
                    """
                    INSERT INTO food_items (
                        name_en, name_he, calories, protein, fat, carbs,
                        unit_weights, unit_synonyms, source
                    )
                    VALUES (
                        :name_en, :name_he, :calories, :protein, :fat, :carbs,
                        CAST(:unit_weights AS jsonb), CAST(:unit_synonyms AS jsonb), 'database'
                    )
                    RETURNING id
                    """
                ),
                {
                    "name_en": item["name_en"],
                    "name_he": item["name_he"],
                    "calories": item["calories"],
                    "protein": item["protein"],
                    "fat": item["fat"],
                    "carbs": item["carbs"],
                    "unit_weights": json.dumps(item["unit_weights"], ensure_ascii=False),
                    "unit_synonyms": json.dumps(item["unit_synonyms"], ensure_ascii=False),
                },
            )
            food_id = food_result.scalar_one()
            foods_inserted += 1

            # Every CSV row has a category, so every food gets a coach mapping
            # (even free / forbidden_main where serving_amount_g is NULL).
            if item["category"] is not None:
                conn.execute(
                    text(
                        """
                        INSERT INTO coach_food_mappings (
                            food_id, coach_id, category, tag, serving_amount_g, notes
                        )
                        VALUES (
                            :food_id, :coach_id, :category, :tag, :serving_amount_g, :notes
                        )
                        """
                    ),
                    {
                        "food_id": str(food_id),
                        "coach_id": str(DEFAULT_COACH_ID),
                        "category": item["category"],
                        "tag": item["tag"],
                        "serving_amount_g": item["serving_amount_g"],
                        "notes": item["notes"],
                    },
                )
                mappings_inserted += 1

        conn.commit()
    engine.dispose()

    return foods_inserted, mappings_inserted


def main():
    parser = argparse.ArgumentParser(description="Seed canonical food catalog into Supabase")
    parser.add_argument(
        "--target",
        choices=["supabase"],
        default="supabase",
        help="Target database (only supabase supported)",
    )
    parser.parse_args()

    items = parse_csv()
    print(f"Parsed {len(items)} food items from {CSV_PATH}")

    foods, mappings = seed_supabase(items)
    print(
        f"Seed complete. Inserted {foods} food_items + {mappings} coach_food_mappings "
        f"under coach_id={DEFAULT_COACH_ID}."
    )


if __name__ == "__main__":
    main()
