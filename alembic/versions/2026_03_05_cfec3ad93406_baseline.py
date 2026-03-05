"""baseline

Revision ID: cfec3ad93406
Revises:
Create Date: 2026-03-05 11:06:42.169080

Baseline migration representing the existing schema + fix food_id nullable.

Tables:
  - food_items: Nutritional data per 100g (CSV-imported)
  - daily_logs: User food log entries with denormalized macros

The food_id column was originally created as NOT NULL but the model was later
updated to nullable=True (for estimated/off-menu items). This migration
corrects the actual DDL to match the model.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cfec3ad93406'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fix food_id to match model (nullable=True for estimated items).
    # render_as_batch=True in env.py enables batch mode for SQLite ALTER support.
    with op.batch_alter_table('daily_logs') as batch_op:
        batch_op.alter_column('food_id', existing_type=sa.INTEGER(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('daily_logs') as batch_op:
        batch_op.alter_column('food_id', existing_type=sa.INTEGER(), nullable=False)
