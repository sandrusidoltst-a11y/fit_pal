from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class FoodItem(Base):
    __tablename__ = "food_items"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True)
    calories = Column(Float)
    protein = Column(Float)
    fat = Column(Float)
    carbs = Column(Float)

    # Relationship: one FoodItem -> many DailyLog entries
    logs = relationship("DailyLog", back_populates="food_item")


class DailyLog(Base):
    """Stores confirmed food entries for long-term tracking."""

    __tablename__ = "daily_logs"

    id = Column(Integer, primary_key=True)
    food_id = Column(Integer, ForeignKey("food_items.id"), nullable=False)
    amount_g = Column(Float, nullable=False)

    # Nutritional values (denormalized for fast aggregation)
    calories = Column(Float, nullable=False)
    protein = Column(Float, nullable=False)
    carbs = Column(Float, nullable=False)
    fat = Column(Float, nullable=False)

    # Temporal data
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    meal_type = Column(String, nullable=True)

    # Audit trail
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Optional: preserve user input
    original_text = Column(String, nullable=True)

    # Relationship
    food_item = relationship("FoodItem", back_populates="logs")
