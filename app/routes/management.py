import json

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError

from app.database import get_database
from app.schemas.results import CandidateDeleteResponse, JobDeleteResponse, ScreeningDetailResponse
from app.schemas.screening import ScreeningAssessment, build_screening_result
from app.services.openrouter_client import OpenRouterError, screen_candidate
from app.services.pii_redactor import redact_personal_information
from app.services.resume_parser import extract_resume_data

router = APIRouter(
    tags=["Management"],
)

def _load_json_object(value: str | None) -> dict:
    """Safely parse stored JSON"""
    if not value:
        return {}

    try:
        parsed_data = json.loads(value)

        if isinstance(parsed_data, dict):
            return parsed_data
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError, RecursionError):
        pass

    return {}

def _get_string_list(data: dict, field_name: str) -> list[str]:
    """Read a list of strings from Json"""
    value = data.get(field_name, [])

    if not isinstance(value, list):
        return []

    return [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]

def _get_screening_detail(connection, result_id: int) -> dict | None:
    row = connection.execute(
        """
        SELECT
            screening_results.id AS screening_result_id,
            screening_results.job_id,
            jobs.title AS job_title,

            screening_results.candidate_id,
            candidates.name AS candidate_name,
            candidates.email,
            candidates.phone,
            candidates.resume_filename,
            candidates.structured_data_json AS candidate_data_json,

            screening_results.required_skills_score,
            screening_results.preferred_skills_score,
            screening_results.experience_score,
            screening_results.education_score,
            screening_results.project_relevance_score,
            screening_results.total_score,

            screening_results.details_json,
            screening_results.justification,
            screening_results.recommendation,

            screening_results.created_at AS screened_at

        FROM screening_results

        INNER JOIN jobs
            ON jobs.id = screening_results.job_id

        INNER JOIN candidates
            ON candidates.id = screening_results.candidate_id

        WHERE screening_results.id = ?
        """,
        (result_id,),
    ).fetchone()

    if row is None:
        return None

    candidate_data = _load_json_object(row["candidate_data_json"])
    details = _load_json_object(row["details_json"])

    return {
        "screening_result_id": row["screening_result_id"],
        "job": {
            "id": row["job_id"],
            "title": row["job_title"],
        },
        "candidate": {
            "id": row["candidate_id"],
            "name": row["candidate_name"],
            "email": row["email"],
            "phone": row["phone"],
            "resume_filename": row["resume_filename"],
            "structured_data": candidate_data,
        },
        "scores": {
            "required_skills_score": row["required_skills_score"],
            "preferred_skills_score": row["preferred_skills_score"],
            "experience_score": row["experience_score"],
            "education_score": row["education_score"],
            "project_relevance_score": row["project_relevance_score"],
            "total_score": row["total_score"],
        },
        "matched_skills": _get_string_list(details, "matched_skills"),
        "missing_required_skills": _get_string_list(
            details,
            "missing_required_skills",
        ),
        "evidence": _get_string_list(details, "evidence"),
        "justification": row["justification"],
        "recommendation": row["recommendation"],
        "screened_at": row["screened_at"],
    }

@router.get(
    "/api/screening-results/{result_id}",
    response_model=ScreeningDetailResponse
)
def get_screening_result(result_id: int):
    """Return one complete candidate screening result."""
    with get_database() as connection:
        detail = _get_screening_detail(connection, result_id)

        if detail is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Screening result not found",
            )

        return detail
@router.delete(
    "/api/candidates/{candidate_id}",
    response_model=CandidateDeleteResponse,
)
def delete_candidate(candidate_id: int):
    """ Delete a candidate and all screening results connected to that candidate."""
    with get_database() as connection:
        candidate = connection.execute(
            """
            SELECT id
            FROM candidates
            WHERE id = ?
            """,
            (candidate_id,),
        ).fetchone()

        if candidate is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidate not found.",
            )

        results_cursor = connection.execute(
            """
            DELETE FROM screening_results
            WHERE candidate_id=?
            """,
            (candidate_id,),
        )

        candidate_cursor = connection.execute(
            """
            DELETE FROM candidates
            WHERE id=?
            """,
            (candidate_id,),
        )

        if candidate_cursor.rowcount != 1:
            raise RuntimeError("Candidate deletion did not complete.")

        return {
            "message": "Candidate deleted successfully.",
            "candidate_id": candidate_id,
            "deleted_results_count": results_cursor.rowcount,
        }

@router.delete(
    "/api/jobs/{job_id}",
    response_model=JobDeleteResponse,
)
def delete_job(job_id: int):
    """ Delete a job, its screening results and candidates that are no longer connected to any result. """
    with get_database() as connection:
        job = connection.execute(
            """
            SELECT id
            FROM jobs
            WHERE id=?
            """,
            (job_id,),
        ).fetchone()

        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )

        candidate_rows = connection.execute(
            """
            SELECT DISTINCT candidate_id
            FROM screening_results
            WHERE job_id=?
            """,
            (job_id,),
        ).fetchall()

        candidate_ids = [
            row["candidate_id"]
            for row in candidate_rows
        ]

        results_cursor = connection.execute(
            """
            DELETE FROM screening_results
            WHERE job_id=?
            """,
            (job_id,),
        )

        job_cursor = connection.execute(
            """
            DELETE FROM jobs
            WHERE id=?
            """,
            (job_id,),
        )

        if job_cursor.rowcount != 1:
            raise RuntimeError("Job deletion did not complete.")

        deleted_orphan_candidates_count = 0

        for candidate_id in candidate_ids:
            remaining_result = connection.execute(
                """
                SELECT 1
                FROM screening_results
                WHERE candidate_id=?
                LIMIT 1
                """,
                (candidate_id,),
            ).fetchone()

            if remaining_result is None:
                cursor = connection.execute(
                    """
                    DELETE FROM candidates
                    WHERE id=?
                      AND NOT EXISTS (
                          SELECT 1
                          FROM screening_results
                          WHERE screening_results.candidate_id = candidates.id
                      )
                    """,
                    (candidate_id,),
                )

                deleted_orphan_candidates_count += (cursor.rowcount)

        return {
            "message": "Job deleted successfully.",
            "job_id": job_id,
            "deleted_results_count": results_cursor.rowcount,
            "deleted_orphan_candidates_count": (
                deleted_orphan_candidates_count
            ),
        }

@router.post(
    "/api/screening-results/{result_id}/rescreen",
    response_model=ScreeningDetailResponse,
)
async def rescreen_candidate(result_id: int):
    """
    Re-screen an existing candidate using the latest screening prompt and current JD
    """
    with get_database() as connection:
        stored_result = connection.execute(
            """
            SELECT
                screening_results.id AS screening_result_id,
                screening_results.job_id,
                screening_results.candidate_id,

                jobs.title AS job_title,
                jobs.description AS job_description,

                candidates.name AS candidate_name,
                candidates.email AS candidate_email,
                candidates.phone AS candidate_phone,
                candidates.resume_text

            FROM screening_results

            INNER JOIN jobs
                ON jobs.id = screening_results.job_id

            INNER JOIN candidates
                ON candidates.id = screening_results.candidate_id

            WHERE screening_results.id = ?
            """,
            (result_id,),
        ).fetchone()

        if stored_result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Screening result not found.",
            )

        resume_text = stored_result["resume_text"]

    parsed_resume = extract_resume_data(resume_text)
    anonymized_resume = redact_personal_information(
        text=resume_text,
        name=parsed_resume.get("name"),
        email=parsed_resume.get("email"),
        phone=parsed_resume.get("phone"),
    )
    anonymized_resume = redact_personal_information(
        text=anonymized_resume,
        name=stored_result["candidate_name"],
        email=stored_result["candidate_email"],
        phone=stored_result["candidate_phone"],
    )

    job_description = (
        f"Job title: {stored_result['job_title']}\n\n"
        "Job description:\n"
        f"{stored_result['job_description']}"
    )

    try:
        service_result = await screen_candidate(
            job_description=job_description,
            anonymized_resume=anonymized_resume,
        )
    except OpenRouterError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error

    if hasattr(service_result, "model_dump"):
        service_data = service_result.model_dump()
    elif isinstance(service_result, dict):
        service_data = service_result
    else:
        service_data = {}

    assessment_data = {
        field_name: service_data[field_name]
        for field_name in ScreeningAssessment.model_fields
        if field_name in service_data
    }

    try:
        assessment = ScreeningAssessment.model_validate(assessment_data)
    except (ValidationError, TypeError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenRouter returned an invalid screening assessment.",
        ) from error

    new_result = build_screening_result(assessment)
    details = {
        "matched_skills": new_result.matched_skills,
        "missing_required_skills": new_result.missing_required_skills,
        "evidence": new_result.evidence,
    }

    with get_database() as connection:
        cursor = connection.execute(
            """
            UPDATE screening_results
            SET
                required_skills_score = ?,
                preferred_skills_score = ?,
                experience_score = ?,
                education_score = ?,
                project_relevance_score = ?,
                total_score = ?,
                details_json = ?,
                justification = ?,
                recommendation = ?
            WHERE id = ?
            """,
            (
                new_result.required_skills_score,
                new_result.preferred_skills_score,
                new_result.experience_score,
                new_result.education_score,
                new_result.project_relevance_score,
                new_result.total_score,
                json.dumps(details),
                new_result.justification,
                new_result.recommendation,
                result_id,
            ),
        )

        if cursor.rowcount != 1:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The screening result could not be updated.",
            )

        detail = _get_screening_detail(connection, result_id)

        if detail is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The updated screening result could not be retrieved.",
            )

        return ScreeningDetailResponse.model_validate(detail)
