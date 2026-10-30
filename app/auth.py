"""Users, passwords (bcrypt), access tokens (JWT, HS256) and role checks as FastAPI dependencies.

Roles: author (uploads, requests, generates), reviewer (records review decisions),
admin (everything, plus user management). Admin satisfies every role check but is still
bound by the separation-of-duties rule in the reviews router.
"""
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import config
from app.audit import append_audit
from app.db import connect_db, now

logger = logging.getLogger("safesop")

ROLES = ("author", "reviewer", "admin")
_bearer = HTTPBearer(auto_error=False)
_fallback_secret = secrets.token_urlsafe(32)


def jwt_secret():
    if config.JWT_SECRET:
        return config.JWT_SECRET
    return _fallback_secret  # warned about at startup: tokens die with the process


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=config.BCRYPT_ROUNDS)).decode("ascii")


def check_password(password, password_hash):
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))


def create_user(username, password, role, created_by):
    username = username.strip()
    if role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(ROLES)}.")
    if not username or len(password) < config.MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400,
                            detail=f"Enter a username and a password of at least {config.MIN_PASSWORD_LENGTH} characters.")
    user = {"id": str(uuid.uuid4()), "username": username, "role": role}
    password_hash = hash_password(password)
    with connect_db() as connection:
        connection.lock_writes()
        if connection.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise HTTPException(status_code=409, detail="That username is taken.")
        connection.execute(
            "INSERT INTO users (id, username, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (user["id"], username, password_hash, role, now()),
        )
        append_audit(connection, created_by, "user_created", "user", user["id"], {"username": username, "role": role})
    return user


def seed_admin():
    """Create the admin named in ADMIN_USERNAME / ADMIN_PASSWORD if it does not exist yet.
    An existing account is never changed, so the env vars cannot reset a password."""
    if not config.JWT_SECRET:
        logger.warning("JWT_SECRET is not set: using a random secret, so logins end when the API restarts.")
    elif len(config.JWT_SECRET.encode("utf-8")) < 32:
        logger.warning("JWT_SECRET is shorter than 32 bytes; use a longer random string.")
    username, password = config.ADMIN_USERNAME, config.ADMIN_PASSWORD
    if not username or not password:
        return
    with connect_db() as connection:
        exists = connection.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
    if not exists:
        create_user(username, password, "admin", created_by="system")
        logger.info("Created admin user %s from ADMIN_USERNAME", username)


def password_hash_of(user_id):
    with connect_db() as connection:
        row = connection.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    return row["password_hash"] if row else None


def authenticate(username, password):
    """The user dict for a correct username/password, else None. Same work either way."""
    with connect_db() as connection:
        row = connection.execute(
            "SELECT id, username, role, password_hash FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
    # Check against a dummy hash for unknown users so response time does not reveal which names exist.
    password_hash = row["password_hash"] if row else _dummy_hash()
    if not check_password(password, password_hash) or not row:
        return None
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


def _dummy_hash():
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password(secrets.token_urlsafe(16))
    return _DUMMY


_DUMMY = None


def issue_token(user):
    expires = datetime.now(timezone.utc) + timedelta(minutes=config.TOKEN_MINUTES)
    return jwt.encode({"sub": user["id"], "exp": expires}, jwt_secret(), algorithm="HS256")


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    """The logged-in user, read fresh from the database (a deleted user's token stops working)."""
    unauthorised = HTTPException(status_code=401, detail="Please sign in.",
                                 headers={"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise unauthorised
    try:
        claims = jwt.decode(credentials.credentials, jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise unauthorised from None
    with connect_db() as connection:
        row = connection.execute("SELECT id, username, role FROM users WHERE id = ?", (claims.get("sub"),)).fetchone()
    if not row:
        raise unauthorised
    return dict(row)


def require_role(*roles):
    """Dependency: the logged-in user, if their role is one of `roles` (admin always passes)."""
    def dependency(user=Depends(current_user)):
        if user["role"] != "admin" and user["role"] not in roles:
            raise HTTPException(status_code=403, detail=f"This needs the {' or '.join(roles)} role.")
        return user
    return dependency
