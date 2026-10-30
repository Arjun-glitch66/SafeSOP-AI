"""Sign-in and user management."""
from fastapi import APIRouter, Depends, HTTPException

from app.auth import authenticate, create_user, current_user, issue_token, require_role
from app.db import connect_db
from app.pagination import page_params, paginate
from app.schemas import LoginRequest, NewUser

router = APIRouter()


@router.post("/api/auth/login")
def login(body: LoginRequest):
    user = authenticate(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Wrong username or password.")
    return {"access_token": issue_token(user), "token_type": "bearer", "user": user}


@router.get("/api/auth/me")
def me(user=Depends(current_user)):
    return user


@router.post("/api/users")
def add_user(body: NewUser, admin=Depends(require_role("admin"))):
    return create_user(body.username, body.password, body.role, created_by=admin["username"])


@router.get("/api/users")
def list_users(page=Depends(page_params), _admin=Depends(require_role("admin"))):
    with connect_db() as connection:
        return paginate(connection, "SELECT id, username, role, created_at FROM users ORDER BY username",
                        (), page, "users")
