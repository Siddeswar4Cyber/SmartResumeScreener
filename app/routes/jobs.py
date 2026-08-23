import json
import sqlite3

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError

from app.database import get_database
from app.schemas.jobs import (
    JobCreateRequest,
    JobRequirements,
    JobResponse,
)

from app.services.job_extractor import extract_job_requirements
from app.services.openrouter_client import OpenRouterError

router = APIRouter(
    prefix="/api/jobs",
    tags=["Jobs"],
)


def _empty_job_requirements() -> JobRequirements:
    return JobRequirements(
        job_summary=""
    )


def _row_to_job_response(row: sqlite3.Row) -> JobResponse:
    """Convert a SQLite job row into a validated API response."""
    try:
        stored_data = json.loads(row["structured_data_json"] or "{}")
        structured_data = JobRequirements.model_validate(stored_data)
    except (json.JSONDecodeError, ValidationError, TypeError):
        structured_data = _empty_job_requirements()

    return JobResponse(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        structured_data=structured_data,
        created_at=row["created_at"],
    )


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    request: JobCreateRequest,
):
    """
    Accept a recruiter-entered JD, extract its requirements and save it.
    """
    try:
        structured_data = await extract_job_requirements(
            title=request.title,
            description=request.description,
        )
    except OpenRouterError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error

    requirements_json = structured_data.model_dump_json()

    with get_database() as connection:
        cursor = connection.execute(
            """
            INSERT INTO jobs (
                title,
                description,
                structured_data_json
            )
            VALUES (?, ?, ?)
            """,
            (
                request.title.strip(),
                request.description.strip(),
                requirements_json,
            ),
        )
        job_id = cursor.lastrowid

        row = connection.execute(
            """
            SELECT
                id,
                title,
                description,
                structured_data_json,
                created_at
            FROM jobs
            WHERE id = ?
            """,
            (job_id,),
        ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The job was saved but could not be retrieved.",
            )

        return _row_to_job_response(row)


@router.get(
    "",
    response_model=list[JobResponse],
)
def list_jobs():
    """Return all saved jobs."""
    with get_database() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                title,
                description,
                structured_data_json,
                created_at
            FROM jobs
            ORDER BY id DESC
            """
        ).fetchall()

        return [_row_to_job_response(row) for row in rows]

@router.get(
    "/{job_id}",
    response_model=JobResponse,
)
def get_job(job_id: int):
    """Return one saved job."""
    with get_database() as connection:
        row = connection.execute(
            """
            SELECT
                id,
                title,
                description,
                structured_data_json,
                created_at
            FROM jobs
            WHERE id = ?
            """,
            (job_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    return _row_to_job_response(row)
