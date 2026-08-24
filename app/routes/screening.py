import json
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.database import get_database
from app.schemas.screening import ScreeningResult
from app.services.file_parser import FileParsingError, MAX_FILE_SIZE, parse_resume_file
from app.services.openrouter_client import OpenRouterError, screen_candidate
from app.services.pii_redactor import redact_personal_information
from app.services.resume_parser import extract_resume_data

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/jobs",
    tags=["Screening"],
)

MAX_RESUMES_PER_REQUEST = 5


def _get_job(job_id: int):
    """Retrieve a saved job from the database."""

    with get_database() as connection:
        job = connection.execute(
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
        return job


def _save_screening_result(
    job_id: int,
    filename: str,
    resume_text: str,
    structured_data: dict,
    screening_result: ScreeningResult,
) -> int:
    """Save the candidate and screening result in one transaction."""

    details = {
        "matched_skills": screening_result.matched_skills,
        "missing_required_skills": screening_result.missing_required_skills,
        "evidence": screening_result.evidence,
    }

    with get_database() as connection:
        candidate_cursor = connection.execute(
            """
            INSERT INTO candidates (
                name,
                email,
                phone,
                resume_filename,
                resume_text,
                structured_data_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                structured_data.get("name") or "Unknown Candidate",
                structured_data.get("email"),
                structured_data.get("phone"),
                filename,
                resume_text,
                json.dumps(structured_data),
            ),
        )

        candidate_id = candidate_cursor.lastrowid

        if candidate_id is None:
            raise RuntimeError("The database did not generate a candidate ID.")

        connection.execute(
            """
            INSERT INTO screening_results (
                job_id,
                candidate_id,
                required_skills_score,
                preferred_skills_score,
                experience_score,
                education_score,
                project_relevance_score,
                total_score,
                details_json,
                justification,
                recommendation
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                candidate_id,
                screening_result.required_skills_score,
                screening_result.preferred_skills_score,
                screening_result.experience_score,
                screening_result.education_score,
                screening_result.project_relevance_score,
                screening_result.total_score,
                json.dumps(details),
                screening_result.justification,
                screening_result.recommendation,
            ),
        )

        return candidate_id


@router.post("/{job_id}/screen")
async def screen_resumes_for_jobs(
    job_id: int,
    files: list[UploadFile] = File(
        ...,
        description="PDF or TXT resumes to screen."
    ),
):
    """Screen multiple resumes against one saved job."""
    job = _get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found."
        )

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload at least one resume."
        )

    if len(files) > MAX_RESUMES_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"A maximum of {MAX_RESUMES_PER_REQUEST}"
                " resumes can be screened at once."
            ),
        )

    successful_results = []
    failed_files = []

    job_description = (
        f"Job title: {job['title']}\n\n"
        f"Job description:\n{job['description']}"
    )

    # Process sequentially to reduce free-model rate-limit errors.

    for uploaded_file in files:
        filename = uploaded_file.filename or "unknown-file"

        try:
            file_content = await uploaded_file.read(MAX_FILE_SIZE + 1)
            parsed_file = parse_resume_file(
                original_filename=filename,
                file_content=file_content,
            )

            structured_data = extract_resume_data(parsed_file.text)
            anonymized_resume = redact_personal_information(
                text=parsed_file.text,
                name=structured_data.get("name"),
                email=structured_data.get("email"),
                phone=structured_data.get("phone"),
            )

            screening_result = await screen_candidate(
                job_description=job_description,
                anonymized_resume=anonymized_resume,
            )

            candidate_id = _save_screening_result(
                job_id=job_id,
                filename=parsed_file.filename,
                resume_text=parsed_file.text,
                structured_data=structured_data,
                screening_result=screening_result,
            )

            successful_results.append(
                {
                    "candidate_id": candidate_id,
                    "filename": parsed_file.filename,
                    "name": structured_data.get("name", "Unknown Candidate"),
                    "email": structured_data.get("email"),
                    "phone": structured_data.get("phone"),
                    "skills": structured_data.get("skills", []),
                    "screening": screening_result.model_dump(),
                }
            )
        except FileParsingError as error:
            failed_files.append(
                {
                    "filename": filename,
                    "stage": "file_parsing",
                    "error": str(error),
                }
            )

        except OpenRouterError as error:
            failed_files.append(
                {
                    "filename": filename,
                    "stage": "screening",
                    "error": str(error),
                }
            )

        except Exception:
            logger.exception(
                "Unexpected screening error for %s", filename
            )

            failed_files.append(
                {
                    "filename": filename,
                    "stage": "unexpected",
                    "error": "An unexpected error occurred while processing this resume.",
                }
            )

        finally:
            await uploaded_file.close()

    if not successful_results:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "None of the resumes could be screened.",
                "failed_files": failed_files,
            },
        )

    return {
        "message": "Resume screening completed.",
        "job": {
            "id": job["id"],
            "title": job["title"],
        },
        "successful_count": len(successful_results),
        "failed_count": len(failed_files),
        "results": successful_results,
        "failed_files": failed_files,
    }
