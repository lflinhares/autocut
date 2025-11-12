# api/schemas.py

from pydantic import BaseModel, Field # <-- IMPORT Field
from typing import List, Optional
from datetime import datetime

# --- Job Schemas ---
# ... (this part remains the same)
class JobBase(BaseModel):
    youtube_url: str

class JobCreate(JobBase):
    pass

class Job(JobBase):
    id: int
    owner_id: int
    status: str
    created_at: datetime
    result_urls: Optional[List[str]] = None

    class Config:
        orm_mode = True

# --- User Schemas ---
class UserBase(BaseModel):
    email: str

class UserCreate(UserBase):
    # THIS IS THE CLASS THAT MATTERS FOR THE /users/ ENDPOINT
    password: str = Field(..., min_length=8, max_length=72) # <--- VERIFY THIS LINE

class User(UserBase):
    id: int
    is_active: bool
    jobs: List[Job] = []

    class Config:
        orm_mode = True
        
# --- Token Schema ---
class Token(BaseModel):
    access_token: str
    token_type: str