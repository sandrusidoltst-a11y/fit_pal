import uuid as uuid_mod
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Uuid, String, Float, Integer, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class FoodItem(Base):
    __tablename__ = "food_items"

    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    calories: Mapped[Optional[float]] = mapped_column(Float)
    protein: Mapped[Optional[float]] = mapped_column(Float)
    fat: Mapped[Optional[float]] = mapped_column(Float)
    carbs: Mapped[Optional[float]] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String, nullable=False, server_default="database")
    user_id: Mapped[Optional[uuid_mod.UUID]] = mapped_column(Uuid, nullable=True, index=True)

    # Relationship: one FoodItem -> many DailyLog entries
    logs: Mapped[list["DailyLog"]] = relationship("DailyLog", back_populates="food_item")


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

    # Temporal data
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
