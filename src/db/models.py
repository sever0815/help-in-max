from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Enum
import os

DATABASE_URL = "sqlite+aiosqlite:///./bot_data.db"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class RequestDB(Base):
    __tablename__ = "requests"
    id = Column(Integer, primary_key=True, index=True)
    beneficiary_id = Column(String)
    volunteer_id = Column(String, nullable=True)
    category = Column(String)
    description = Column(String)
    address = Column(String)
    scheduled_time = Column(String)  # Добавили колонку
    status = Column(String)

class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True)
    username = Column(String, nullable=True, index=True)
    role = Column(String) # "admin", "volunteer", "beneficiary"

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
