"""Sign-in, own password, and user management (admin)."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import (
    authenticate,
    check_password,
    create_user,
    current_user,
    issue_token,
    password_hash_of,
    require_role,
    set_password,
    set_role,
)
from app.db import connect_db
from app.limits import check_login_allowed, clear_login_failures, record_login_failure
from app.pagination import page_params, paginate
from app.schemas import LoginRequest, NewUser, PasswordChange, UserUpdate

logger = logging.getLogger("safesop")
router = APIRouter()


def client_address(request: Request):
    return request.client.host if request.client else "unknown"


@router.post("/api/auth/login")
def login(body: LoginRequest, request: Request):
    client = client_address(request)
    check_login_allowed(body.username, client)  # 429 while this name or address is guessing
    user = authenticate(body.username, body.password)
    if not user:
        record_login_failure(body.username, client)
        logger.warning("Failed sign-in for username %r from %s", body.username[:100], client)
        raise HTTPException(status_code=401, detail="Wrong username or password.")
    clear_login_failures(body.username)
    return {"access_token": issue_token(user), "token_type": "bearer", "user": user}


@router.get("/api/auth/me")
def me(user=Depends(current_user)):
    return user


@router.post("/api/auth/password")
def change_own_password(body: PasswordChange, request: Request, user=Depends(current_user)):
    """Change your own password. Needs the current one; ends your other sessions, so a new token is returned."""
    client = client_address(request)
    check_login_allowed(user["username"], client)
    if not check_password(body.current_password, password_hash_of(user["id"]) or ""):
        record_login_failure(user["username"], client)
        raise HTTPException(status_code=403, detail="Your current password is not correct.")
    set_password(user["id"], body.new_password, actor=user["username"], action="password_changed")
    clear_login_failures(user["username"])
    return {"access_token": issue_token(user), "token_type": "bearer", "user": user}


@router.post("/api/users")
def add_user(body: NewUser, admin=Depends(require_role("admin"))):
    return create_user(body.username, body.password, body.role, created_by=admin["username"])


@router.get("/api/users")
def list_users(page=Depends(page_params), _admin=Depends(require_role("admin"))):
    with connect_db() as connection:
        return paginate(connection, "SELECT id, username, role, created_at FROM users ORDER BY username",
                        (), page, "users")


@router.patch("/api/users/{user_id}")
def update_user(user_id: str, body: UserUpdate, admin=Depends(require_role("admin"))):
    """Change a user's role and/or set a new password (an admin reset). Both are audited;
    a reset ends that user's sessions. The last admin cannot be demoted."""
    if body.role is None and body.password is None:
        raise HTTPException(status_code=400, detail="Send a new role, a new password, or both.")
    if body.password is not None:
        set_password(user_id, body.password, actor=admin["username"], action="user_password_reset")
        clear_login_failures(_username(user_id))
    if body.role is not None:
        return set_role(user_id, body.role, actor=admin["username"])
    with connect_db() as connection:
        return dict(connection.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,)).fetchone())


def _username(user_id):
    with connect_db() as connection:
        row = connection.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    return row["username"] if row else ""
