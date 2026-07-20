from sqlalchemy import Column, Integer, String
from database import Base  # Import the Base class from your database file


class FoodLog(Base):
    __tablename__ = "food_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    date = Column(String, index=True)
    food_name = Column(String, nullable=False)
    meal_type = Column(String, nullable=True)
    calories = Column(Integer, default=0)
    protein = Column(Integer, default=0)
    carbs = Column(Integer, default=0)
    fats = Column(Integer, default=0)
