"""Per-user limits on the billed /generate call: a per-minute rate and a daily quota.

ponytail: the per-minute window lives in this process's memory (one API process). With several
API processes behind a load balancer, move it to Redis or the database. The daily quota is
counted from the jobs table, so it already holds across processes and restarts.
"""
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app import config
from app.db import connect_db

_recent: defaultdict[str, deque[float]] = defaultdict(deque)  # username -> monotonic times of recent /generate calls
_lock = threading.Lock()


def check_generate_allowed(username):
    """Raise 429 (with Retry-After) if this user is over the per-minute rate or the daily quota."""
    per_minute, per_day = config.GENERATE_PER_MINUTE, config.GENERATE_PER_DAY

    if per_day:
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        with connect_db() as connection:
            used = connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE created_by = ? AND created_at >= ?",
                (username, day_start.isoformat()),
            ).fetchone()[0]
        if used >= per_day:
            retry = int((day_start + timedelta(days=1) - datetime.now(timezone.utc)).total_seconds()) + 1
            raise HTTPException(status_code=429, headers={"Retry-After": str(retry)},
                                detail=f"Daily generation quota reached ({per_day} per user per day, UTC). "
                                       "Ask an admin to raise GENERATE_PER_DAY if you need more.")

    if per_minute:
        now = time.monotonic()
        with _lock:
            calls = _recent[username]
            while calls and now - calls[0] >= 60:
                calls.popleft()
            if len(calls) >= per_minute:
                retry = int(60 - (now - calls[0])) + 1
                raise HTTPException(status_code=429, headers={"Retry-After": str(retry)},
                                    detail=f"Too many generations: at most {per_minute} per minute. "
                                           f"Try again in {retry} s.")
            calls.append(now)


def reset():
    """Forget the per-minute windows and sign-in failures (tests)."""
    with _lock:
        _recent.clear()
        _failures.clear()


# ---- Sign-in and approval-signature throttling ----
# ponytail: in-process like the per-minute window above (one API process). A failure limit per
# username stops guessing one account's password; a looser limit per client address stops
# spraying many accounts. A success clears that username's failures.
_failures: defaultdict[str, deque[float]] = defaultdict(deque)


def _recent_failures(key, now):
    window = _failures[key]
    while window and now - window[0] >= config.LOGIN_WINDOW_SECONDS:
        window.popleft()
    return window


def check_login_allowed(username, client):
    """Raise 429 (with Retry-After) while this username or client address has too many recent failures."""
    now = time.monotonic()
    limits = ((f"user:{username.strip().lower()}", config.LOGIN_MAX_FAILURES),
              (f"client:{client}", config.LOGIN_MAX_FAILURES_PER_CLIENT))
    with _lock:
        for key, limit in limits:
            window = _recent_failures(key, now)
            if limit and len(window) >= limit:
                retry = int(config.LOGIN_WINDOW_SECONDS - (now - window[0])) + 1
                raise HTTPException(status_code=429, headers={"Retry-After": str(retry)},
                                    detail=f"Too many failed attempts. Try again in {max(1, retry // 60)} minute(s).")


def record_login_failure(username, client):
    now = time.monotonic()
    with _lock:
        _failures[f"user:{username.strip().lower()}"].append(now)
        _failures[f"client:{client}"].append(now)


def clear_login_failures(username):
    with _lock:
        _failures.pop(f"user:{username.strip().lower()}", None)
