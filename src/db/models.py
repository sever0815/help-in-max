import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, text

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:////app/bot_data.db")

engine = create_async_engine(DATABASE_URL, echo=True)
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
    scheduled_time = Column(String)
    status = Column(String)

class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    # Идентификатор пользователя в мессенджере (MAX и т.п.)
    platform_user_id = Column(String, unique=True, index=True)
    username = Column(String, nullable=True, index=True)
    role = Column(String)  # "superadmin", "admin", "volunteer", "beneficiary"

async def _migrate_legacy_columns(conn):
    """Переименование старых telegram-колонок, чтобы не терять данные при обновлении."""
    res = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    )
    if res.scalar_one_or_none() is None:
        return
    res = await conn.execute(text("PRAGMA table_info(users)"))
    cols = {row[1] for row in res.fetchall()}
    if "platform_user_id" not in cols and "telegram_id" in cols:
        await conn.execute(text("ALTER TABLE users RENAME COLUMN telegram_id TO platform_user_id"))

async def init_db():
    async with engine.begin() as conn:
        # Создаем таблицы, если их нет
        await conn.run_sync(Base.metadata.create_all)
        # Обрабатываем старые колонки, если база уже была
        await _migrate_legacy_columns(conn)
