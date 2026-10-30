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
    """Forget the per-minute windows (tests)."""
    with _lock:
        _recent.clear()
