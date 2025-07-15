from pydantic import BaseModel
from typing import Optional
import uuid

class UserBase(BaseModel):
    """
    Base schema for user data.
    """
    username: str
    email: str # <-- Add email to the base

class UserCreate(UserBase):
    """
    Schema for creating a new user.
    """
    password: str

class User(UserBase):
    """
    Schema representing a user.
    """
    id: uuid.UUID
    full_name: Optional[str] = None # <-- Add full_name

    class Config:
        from_attributes = True

class Token(BaseModel):
    """
    Schema for authentication token.
    """
    access_token: str
    token_type: str

class TokenData(BaseModel):
    """
    Schema for token data.
    """
    username: Optional[str] = None