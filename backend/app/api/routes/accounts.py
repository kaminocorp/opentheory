from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession
from app.core.config import settings
from app.models.account import Account
from app.schemas.account import AccountCreate, AccountRead
from app.services import account as account_service

router = APIRouter()


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(payload: AccountCreate, db: DbSession) -> Account:
    # Dev/test bootstrap only: real accounts are JIT-provisioned from a verified token on sign-in
    # (api/deps.py). The open bootstrap survives only behind the dev flag, for local work + tests
    # (e.g. building an internal funder to exercise native funding).
    if not settings.auth_dev_header_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account creation is automatic on sign-in; this bootstrap route is disabled",
        )
    return await account_service.create_account(db, payload)


@router.get("", response_model=list[AccountRead])
async def list_accounts(db: DbSession) -> list[Account]:
    # Dev-gated (PII): AccountRead exposes external_id + the verified email + roles — the 0.6.1
    # email-harvest leak class, which moved here with those fields. An open list would expose every
    # principal's IdP subject, email, and roles to any anonymous caller. Disabled in production.
    if not settings.auth_dev_header_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account listing is disabled; identity is resolved per-request from the token",
        )
    return await account_service.list_accounts(db)
