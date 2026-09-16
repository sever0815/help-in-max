from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime

class RequestStatus(str, Enum):
    NEW = "new"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class RequestCategory(str, Enum):
    PRODUCTS = "products"      # Продукты
    WALK = "walk"              # Прогулка
    CLEANING = "cleaning"      # Уборка
    OTHER = "other"            # Другое

class Request(BaseModel):
    id: Optional[int] = None
    beneficiary_id: str
    volunteer_id: Optional[str] = None
    category: RequestCategory
    description: str
    address: str
    status: RequestStatus = RequestStatus.NEW
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
