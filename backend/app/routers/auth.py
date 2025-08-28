from app.auth import make_token, check_pw, get_current_user, hash_pw
from app.db import SessionLocal  # dein async sessionmaker
from fastapi import APIRouter, Depends
from models import User
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

router = APIRouter(prefix="")


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/login")
async def login(body: LoginIn):
    async with SessionLocal() as db:
        q = await db.execute(select(User).where(User.email == body.email))
        u = q.scalar_one_or_none()
        if not u or not check_pw(body.password, u.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return {"access_token": make_token(u), "token_type": "bearer", "role": u.role, "team_id": u.team_id}


@router.get("/me")
async def me(u: User = Depends(get_current_user)):
    return {"id": u.id, "email": u.email, "role": u.role, "team_id": u.team_id}
