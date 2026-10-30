import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool

from app.routes import calls, tools

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://voice:voice@localhost:5433/voice_intake")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncConnectionPool(
        DATABASE_URL, min_size=1, max_size=10, kwargs={"autocommit": True}, open=False
    ) as pool:
        app.state.pool = pool
        yield


app = FastAPI(title="Voice Intake Backend", lifespan=lifespan)
app.include_router(calls.router)
app.include_router(tools.router)
