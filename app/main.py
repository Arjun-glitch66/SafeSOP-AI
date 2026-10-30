"""FastAPI application: middleware, startup migration and routers."""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.auth import current_user, seed_admin
from app.db import init_db
from app.routers import audit, auth, documents, health, requests, reviews, versions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("safesop")


@asynccontextmanager
async def lifespan(_app):
    init_db()
    seed_admin()
    logger.info("SafeSOP API started. Database: %s", config.DB_PATH)
    yield


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

app.include_router(health.router)  # public: liveness and evaluator status
app.include_router(auth.router)    # login is public; the rest checks roles itself
# Everything else needs a signed-in user; write endpoints add a role check of their own.
for module in (documents, requests, versions, reviews, audit):
    app.include_router(module.router, dependencies=[Depends(current_user)])
