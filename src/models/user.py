from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime

class UserRole(str, Enum):
    BENEFICIARY = "beneficiary"
    VOLUNTEER = "volunteer"

class User(BaseModel):
    id: str
    username: Optional[str] = None
    role: UserRole
    full_name: Optional[str] = None
