from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

router = APIRouter(
    tags=["Fronted"],
)

FRONTEND_DIRECTORY = (
    Path(__file__).resolve().parents[2] / "frontend"
)
DASHBOARD_PATH = FRONTEND_DIRECTORY / "index.html"

@router.get(
    "/dashboard",
    include_in_schema=False
)
def dashboard():
    "Serve the resume screen dashboard."
    if not DASHBOARD_PATH.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard frontend is unavailable.",
        )

    return FileResponse(
        DASHBOARD_PATH,
        media_type="text/html",
    )
