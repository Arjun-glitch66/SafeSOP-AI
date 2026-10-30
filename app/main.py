"""FastAPI application: middleware, startup migration and routers."""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.auth import current_user, seed_admin
from app.db import init_db
from app.logging_setup import configure_logging
from app.services import jobs
from app.routers import audit, auth, documents, health, requests, reviews, versions

configure_logging()
logger = logging.getLogger("safesop")
access_logger = logging.getLogger("safesop.access")


@asynccontextmanager
async def lifespan(_app):
    init_db()
    seed_admin()
    jobs.fail_interrupted_jobs()
    logger.info("SafeSOP API started. Database: %s", config.DB_PATH)
    yield
    jobs.shutdown()


app = FastAPI(
    title="SafeSOP AI API",
    description="Document storage and revision workflow API",
    version="1.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """One structured line per request (no bodies, no tokens)."""
    started = time.perf_counter()
    response = await call_next(request)
    access_logger.info("request", extra={
        "method": request.method, "path": request.url.path, "status": response.status_code,
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
    })
    return response


app.include_router(health.router)  # public: liveness and evaluator status
app.include_router(auth.router)    # login is public; the rest checks roles itself
# Everything else needs a signed-in user; write endpoints add a role check of their own.
for module in (documents, requests, versions, reviews, audit):
    app.include_router(module.router, dependencies=[Depends(current_user)])
