"""One-shot helper: convert canonical_food_catalog.csv to unit_weights JSON.

Transforms the CSV column pair (`default_unit`, `default_unit_weight_g`) into
two JSON-encoded columns (`unit_weights`, `unit_synonyms`). Idempotent — if the
new columns are already present and populated, the row is left untouched.

Writes the result back to the same CSV path. Run before re-seeding from the
new format.

Usage:
    uv run python src/scripts/migrate_csv_to_unit_weights.py
"""

import csv
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.config import BASE_DIR

CSV_PATH = os.path.join(BASE_DIR, "data", "canonical_food_catalog.csv")


def _to_unit_weights(default_unit: str | None, default_unit_weight_g: str | None) -> str:
    """Build the JSON-encoded unit_weights value from the legacy pair."""
    if not default_unit:
        return "{}"
    unit = default_unit.strip()
    if not unit or unit == "g":
        # gram-native foods carry no natural-unit weight
        return "{}"
    if not default_unit_weight_g:
        return "{}"
    try:
        weight = float(default_unit_weight_g)
    except (TypeError, ValueError):
        return "{}"
    return json.dumps({unit: weight}, ensure_ascii=False)


def migrate(path: str = CSV_PATH) -> tuple[int, int]:
    """Rewrite the CSV in place. Returns (rows_total, rows_with_unit_weights)."""
    with open(path, mode="r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        original_fieldnames = list(reader.fieldnames or [])

    if not rows:
        print(f"No rows found in {path}; nothing to migrate.")
        return 0, 0

    new_fieldnames = [
        f for f in original_fieldnames if f not in {"default_unit", "default_unit_weight_g"}
    ]
    # Insert the new columns where the old ones used to live (preserves coach mental model).
    insert_at = len(new_fieldnames)
    for marker in ("default_unit", "default_unit_weight_g"):
        if marker in original_fieldnames:
            insert_at = original_fieldnames.index(marker)
            break
    for new_col in ("unit_weights", "unit_synonyms"):
        if new_col not in new_fieldnames:
            new_fieldnames.insert(insert_at, new_col)
            insert_at += 1

    populated = 0
    for row in rows:
        existing = (row.get("unit_weights") or "").strip()
        if existing and existing != "{}":
            # Already migrated — leave as-is.
            row.setdefault("unit_synonyms", "{}")
            populated += 1
        else:
            row["unit_weights"] = _to_unit_weights(
                row.get("default_unit"), row.get("default_unit_weight_g")
            )
            row.setdefault("unit_synonyms", "{}")
            if row["unit_weights"] != "{}":
                populated += 1
        row.pop("default_unit", None)
        row.pop("default_unit_weight_g", None)

    with open(path, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=new_fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows), populated


def main() -> None:
    total, with_units = migrate()
    print(
        f"Migrated {total} rows in {CSV_PATH} ({with_units} now carry unit_weights)."
    )


if __name__ == "__main__":
    main()
