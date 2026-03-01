from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class FoodItem(Base):
    __tablename__ = "food_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    calories: Mapped[Optional[float]] = mapped_column(Float)
    protein: Mapped[Optional[float]] = mapped_column(Float)
    fat: Mapped[Optional[float]] = mapped_column(Float)
    carbs: Mapped[Optional[float]] = mapped_column(Float)

    # Relationship: one FoodItem -> many DailyLog entries
    logs: Mapped[list["DailyLog"]] = relationship("DailyLog", back_populates="food_item")


class DailyLog(Base):
    """Stores confirmed food entries for long-term tracking."""

    __tablename__ = "daily_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    food_id: Mapped[int] = mapped_column(Integer, ForeignKey("food_items.id"), nullable=False)
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
