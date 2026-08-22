# app/main.py

from fastapi import FastAPI, HTTPException, status
from app.database import database_is_available, initialize_database
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    '''
    Intialize application resources during setup

    code before yield runs when server start
    code after yield would runs when server stop
    '''
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

@app.get("/",tags=["General"])
def root():
    """ Return basic information about the application. """
    return {
        "message": "Smart Resume Screener API is running.",
        "documentation": "/docs",
    }

@app.get("/api/health", tags=["General"])
def health_check():
    """ Check whether the backend serivices is avaiable and running. """
    if not database_is_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail = "Database is unavailable"
        )
    return {
        "status": "healthy",
        "service": "Smart Resume Screener API",
        "version": "1.0.0",
        "database": "connected",
    }