from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import Base, engine
from .routes import auth_routes, diagnostic, reports, dashboard
from .config import get_secret_key

Base.metadata.create_all(bind=engine)


def validate_startup_configuration():
    """Validates critical security configuration at server startup.

    Fails fast with a clear RuntimeError if SECRET_KEY is missing,
    insecure, or invalid, preventing the server from accepting traffic
    and crashing with runtime HTTP 500 errors during authentication.
    """
    get_secret_key()


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_startup_configuration()
    yield


app = FastAPI(title="AI Pulse API", lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(diagnostic.router)
app.include_router(reports.router)
app.include_router(dashboard.router)


@app.get("/health")
def health():
    return {"status": "ok"}
