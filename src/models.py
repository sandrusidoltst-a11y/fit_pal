import uuid as uuid_mod
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Uuid, String, Float, Integer, DateTime, Text, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class FoodItem(Base):
    __tablename__ = "food_items"

    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    name_en: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    name_he: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    calories: Mapped[Optional[float]] = mapped_column(Float)
    protein: Mapped[Optional[float]] = mapped_column(Float)
    fat: Mapped[Optional[float]] = mapped_column(Float)
    carbs: Mapped[Optional[float]] = mapped_column(Float)
    unit_weights: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    unit_synonyms: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    source: Mapped[str] = mapped_column(String, nullable=False, server_default="database")
    user_id: Mapped[Optional[uuid_mod.UUID]] = mapped_column(Uuid, nullable=True, index=True)

    # Relationship: one FoodItem -> many DailyLog entries
    logs: Mapped[list["DailyLog"]] = relationship("DailyLog", back_populates="food_item")
    coach_mappings: Mapped[list["CoachFoodMapping"]] = relationship(
        "CoachFoodMapping", back_populates="food_item", cascade="all, delete-orphan"
    )


class DailyLog(Base):
    """Stores confirmed food entries for long-term tracking."""

    __tablename__ = "daily_logs"

    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    food_id: Mapped[Optional[uuid_mod.UUID]] = mapped_column(Uuid, ForeignKey("food_items.id"), nullable=True)
    user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, nullable=False, index=True)
    amount_g: Mapped[float] = mapped_column(Float, nullable=False)

    # Nutritional values (denormalized for fast aggregation)
    calories: Mapped[float] = mapped_column(Float, nullable=False)
    protein: Mapped[float] = mapped_column(Float, nullable=False)
    carbs: Mapped[float] = mapped_column(Float, nullable=False)
    fat: Mapped[float] = mapped_column(Float, nullable=False)

    # Temporal data — filter by local-day via timestamp_in_local_day from src.config.
    # Never use func.date(timestamp) == ...: it evaluates in the DB session timezone (UTC), not user-local.
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    meal_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Audit trail
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Optional: preserve user input
    original_text: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Relationship
    food_item: Mapped["FoodItem"] = relationship("FoodItem", back_populates="logs")


class UserProfile(Base):
    """Stores user identity data set during onboarding."""

    __tablename__ = "user_profiles"

    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String, nullable=False)
    nutrition_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class PersonalStatsLog(Base):
    """Stores time-series body measurements (weight, body fat %)."""

    __tablename__ = "personal_stats_log"

    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, nullable=False, index=True)
    weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    body_fat_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class CoachFoodMapping(Base):
    """Coach-method-specific overlay on top of universal food data.

    One row per (food_id, coach_id) tuple — multiple coaches can map the same food
    differently (different categories, serving sizes per their methods).
    """

    __tablename__ = "coach_food_mappings"

    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    food_id: Mapped[uuid_mod.UUID] = mapped_column(
        Uuid, ForeignKey("food_items.id"), nullable=False, index=True
    )
    coach_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String, nullable=False)  # CHECK constraint enforced in Postgres
    tag: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    serving_amount_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    food_item: Mapped["FoodItem"] = relationship("FoodItem", back_populates="coach_mappings")

    __table_args__ = (UniqueConstraint("food_id", "coach_id", name="uq_coach_food_mappings_food_coach"),)
