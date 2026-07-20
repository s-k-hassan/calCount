from pydantic import BaseModel


class FoodLogCreate(BaseModel):
    date: str
    food_name: str
    calories: int
    protein: int
    carbs: int
    fats: int


class FoodLogResponse(FoodLogCreate):
    id: int

    class Config:
        from_attributes = True
