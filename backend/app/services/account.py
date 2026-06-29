from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.schemas.account import AccountCreate


async def create_account(db: AsyncSession, payload: AccountCreate) -> Account:
    """Dev/test bootstrap (behind ``auth_dev_header_enabled``). Production accounts are
    JIT-provisioned with their primary human Actor on first sign-in (``api/deps.py``); this exists
    only so tests can build an internal funder without seeding (Decision #8)."""
    account = Account(**payload.model_dump())
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def list_accounts(db: AsyncSession) -> list[Account]:
    result = await db.execute(select(Account).order_by(Account.created_at.desc()))
    return list(result.scalars())
