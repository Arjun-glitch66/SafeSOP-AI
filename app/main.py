"""FastAPI application: middleware, startup migration and routers."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.db import init_db
from app.routers import documents, health, requests, reviews, versions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("safesop")


@asynccontextmanager
async def lifespan(_app):
    init_db()
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

for module in (health, documents, requests, versions, reviews):
    app.include_router(module.router)
