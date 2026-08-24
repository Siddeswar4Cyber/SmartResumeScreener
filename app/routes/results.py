import json

from fastapi import APIRouter, HTTPException, status

from app.database import get_database
from app.schemas.results import JobRankingResponse

router = APIRouter(
    prefix="/api/jobs",
    tags=["Results"],
)

def _load_json_object(value: str | None) -> dict:
    if not value:
        return {}

    try:
        parsed_data = json.loads(value)

        if isinstance(parsed_data, dict):
            return parsed_data

    except (json.JSONDecodeError, TypeError):
        pass

    return  {}

def _get_string_list(
    data: dict,
    field_name: str
) -> list[str]:
    value = data.get(field_name,[])

    if not isinstance(value, list):
        return []
    return [
        item.strip()
        for item in value
        if isinstance(item,str) and item.strip()
    ]

@router.get(
    "/{job_id}/results",
    response_model=JobRankingResponse
)

def get_ranked_job_results(job_id: int):
    with get_database() as connection:
        job = connection.execute(
            """
            SELECT
                id,
                title
            FROM jobs
            WHERE id = ?
            """,
            (job_id,)
        ).fetchone()

        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="job not found."
            )

        rows = connection.execute(
            """
            SELECT
                screening_results.id AS screening_result_id,
                screening_results.candidate_id AS candidate_id,
                candidates.name AS candidate_name,
                candidates.email AS email,
                candidates.phone AS phone,
                candidates.resume_filename AS resume_filename,
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

            INNER JOIN candidates
                ON candidates.id = screening_results.candidate_id
            
            WHERE screening_results.job_id = ?

            ORDER BY
                screening_results.total_score DESC,
                screening_results.required_skills_score DESC,
                screening_results.experience_score DESC,
                screening_results.created_at ASC,
                screening_results.id ASC
            """,
            (job_id,),
        ).fetchall()
    
        ranked_results = []
        for rank, row in enumerate(rows, start=1):
            candidate_data = _load_json_object(row["candidate_data_json"])
            details = _load_json_object(row["details_json"])

            ranked_results.append(
                {
                    "rank": rank,
                    "screening_result_id": row["screening_result_id"],
                    "candidate_id": row["candidate_id"],
                    "candidate_name": row["candidate_name"],
                    "email": row["email"],
                    "phone": row["phone"],
                    "resume_filename": row["resume_filename"],
                    "skills": _get_string_list(candidate_data,"skills"),
                    "scores": {
                        "required_skills_score": row["required_skills_score"],
                        "preferred_skills_score": row["preferred_skills_score"],
                        "experience_score": row["experience_score"],
                        "education_score": row["education_score"],
                        "project_relevance_score": row["project_relevance_score"],
                        "total_score": row["total_score"], 
                    },
                    "matched_skills": _get_string_list(details,"matched_skills"),
                    "missing_required_skills": _get_string_list(details,"missing_required_skills"),
                    "evidence": _get_string_list(details,"evidence"),
                    "justification": row["justification"],
                    "recommendation": row["recommendation"],
                    "screened_at": row["screened_at"],
                }
            )

        return {
            "job_id" : job["id"],
            "job_title": job["title"],
            "candidate_count": len(ranked_results),
            "results": ranked_results
        }