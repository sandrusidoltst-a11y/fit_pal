from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import DeclarativeBase

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
