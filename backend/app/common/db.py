from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.common.config import DATABASE_URL, DEV_MODE

engine = create_async_engine(DATABASE_URL, echo=DEV_MODE)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def get_db():
    async with async_session() as session:
        yield session

class Base(DeclarativeBase):
    pass
