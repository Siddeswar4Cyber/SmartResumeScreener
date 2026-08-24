# app/main.py

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status

from app.database import database_is_available, initialize_database
from app.routes.jobs import router as jobs_router
from app.routes.resumes import router as resume_router
from app.routes.screening import router as screening_router
from app.routes.results import router as results_router
from app.routes.management import router as management_router

from fastapi.staticfiles import StaticFiles
from app.routes.frontend import FRONTEND_DIRECTORY, router as frontend_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize application resources during startup."""

    initialize_database()
    yield


app = FastAPI(
    title="Smart Resume Screener API",
    description=(
        "API for extracting resume information and matching candidates against job descriptions."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/", tags=["General"])
def root():
    """Return basic information about the application."""
    return {
        "message": "Smart Resume Screener API is running.",
        "documentation": "/docs",
    }


@app.get("/api/health", tags=["General"])
def health_check():
    """Check whether the database is available."""
    if not database_is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        )
    return {
        "status": "healthy",
        "service": "Smart Resume Screener API",
        "version": "1.0.0",
        "database": "connected",
    }

app.include_router(resume_router)
app.include_router(jobs_router)
app.include_router(screening_router)
app.include_router(results_router)
app.include_router(management_router)

if FRONTEND_DIRECTORY.is_dir():
    app.mount(
        "/static",
        StaticFiles(directory=FRONTEND_DIRECTORY),
        name="static",
    )

app.include_router(frontend_router)
