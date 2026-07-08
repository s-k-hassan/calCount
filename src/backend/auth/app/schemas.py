from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserResponse(UserCreate):
    id: int
    email: EmailStr
    is_active: bool

    class Config:
        from_attributes = True

class UserPasswordChange(BaseModel):
    current_password: str
    new_password: str