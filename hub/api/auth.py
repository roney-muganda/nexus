import random
import string
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from hub.models.database import get_db
from datetime import datetime, timezone, timedelta
from hub.models.telegram_link import TelegramLink
from hub.models.user import User
from hub.models.user_preferences import UserPreferences
from hub.auth.password import hash_password, verify_password
from hub.auth.jwt_handler import create_access_token
from hub.auth.dependencies import get_current_user

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    await db.flush()

    prefs = UserPreferences(user_id=user.id)
    db.add(prefs)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(
        user_id=str(user.id),
        device_id="web",
        scopes=["read:memory", "write:tasks", "execute:commands"]
    )
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )

    token = create_access_token(
        user_id=str(user.id),
        device_id="web",
        scopes=["read:memory", "write:tasks", "execute:commands"]
    )
    return TokenResponse(access_token=token)


@router.get("/me")
async def get_me(db: AsyncSession = Depends(get_db)):
    return {"message": "auth working"}

@router.post("/telegram/generate-link-code")
async def generate_telegram_link_code(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # invalidate any existing unused codes for this user
    from sqlalchemy import update
    await db.execute(
        update(TelegramLink)
        .where(
            TelegramLink.user_id == current_user.id,
            TelegramLink.used == False
        )
        .values(used=True)
    )

    # generate a new 6-digit code
    code = "".join(random.choices(string.digits, k=6))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    link = TelegramLink(
        user_id=current_user.id,
        code=code,
        expires_at=expires_at,
    )
    db.add(link)
    await db.commit()

    return {
        "code": code,
        "expires_in_minutes": 10,
        "instruction": f"Send this to your Telegram bot: /link {code}"
    }


@router.get("/telegram/status")
async def get_telegram_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from hub.models.user_preferences import UserPreferences
    result = await db.execute(
        select(UserPreferences).where(
            UserPreferences.user_id == current_user.id
        )
    )
    prefs = result.scalar_one_or_none()
    linked = prefs and prefs.telegram_chat_id is not None
    return {
        "telegram_linked": linked,
        "telegram_chat_id": prefs.telegram_chat_id if linked else None
    }