import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.db import settings
from app.models import Base, Entity, IntercompanyTransaction

@pytest.fixture
async def db():
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        entity_a = Entity(name="Test A", jurisdiction="KE", entity_type="opco")
        entity_b = Entity(name="Test B", jurisdiction="UK", entity_type="opco")
        session.add_all([entity_a, entity_b])
        await session.flush()
        tx = IntercompanyTransaction(from_entity_id=entity_a.id,to_entity_id=entity_b.id,type="services",
            amount=100,currency="USD",transaction_date=__import__("datetime").date.today(),
            stated_price=100,benchmark_low=90,benchmark_high=110)
        session.add(tx)
        await session.flush()
        yield session
        await session.rollback()
    await engine.dispose()
