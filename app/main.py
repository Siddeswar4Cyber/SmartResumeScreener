# app/main.py

from fastapi import FastAPI

app = FastAPI(
    title="Smart Resume Screener API",
    description=(
        "API for extracting resume information and matching candidates against job descriptions."
    ),
    version="1.0.0",
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
    return {
        "status": "healthy",
        "service": "Smart Resume Screener API",
        "version": "1.0.0",
    }