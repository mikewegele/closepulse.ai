import bcrypt
import jwt
import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from models import User
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGO = "HS256"
ACCESS_TTL_MIN = int(os.getenv("ACCESS_TTL_MIN", "120"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


class TokenData(BaseModel):
    sub: str
    role: str
    team_id: str


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_pw(pw: str, ph: str) -> bool:
    return bcrypt.checkpw(pw.encode(), ph.encode())


def make_token(u: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": u.id,
        "role": u.role,
        "team_id": u.team_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TTL_MIN)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = None):
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    q = await db.execute(select(User).where(User.id == data["sub"]))
    u = q.scalar_one_or_none()
    if not u: raise HTTPException(status_code=401, detail="User not found")
    return u


def require_role(*roles: str):
    async def dep(u: User = Depends(get_current_user)):
        if u.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return u

    return dep
