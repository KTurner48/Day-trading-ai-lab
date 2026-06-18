"""Auth routes: login returns a JWT; /me returns the current user."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthError, get_current_user
from app.core.security import create_access_token, verify_password
from app.models.db import User, get_db

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginBody(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginBody, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(
        select(User).where(User.email == body.email)
    )).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise AuthError("Invalid email or password")
    return TokenResponse(access_token=create_access_token(user.email))


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "role": user.role,
            "full_name": user.full_name}
