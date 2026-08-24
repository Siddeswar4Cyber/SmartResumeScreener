from typing import Optional, Any
from pydantic import BaseModel, Field

class ScoreBreakdown(BaseModel):
    required_skills_score: int
    preferred_skills_score: int
    experience_score: int
    education_score: int
    project_relevance_score: int
    total_score: int

class RankedCandidateResponse(BaseModel):
    rank: int
    screening_result_id: int
    candidate_id: int

    candidate_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    resume_filename: str
    skills: list[str] = Field(default_factory=list)

    scores: ScoreBreakdown

    matched_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    justification: Optional[str] = None
    recommendation: Optional[str] = None
    screened_at: Optional[str] = None

class JobRankingResponse(BaseModel):
    job_id: int
    job_title: str
    candidate_count: int
    results: list[RankedCandidateResponse]

class JobReference(BaseModel):
    id: int
    title: str

class CandidateResponse(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    resume_filename: str
    structured_data : dict[str, Any] = Field(default_factory=dict)

class ScreeningDetailResponse(BaseModel):
    screening_result_id: int
    job: JobReference
    candidate: CandidateResponse
    scores: ScoreBreakdown

    matched_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)

    justification: str
    recommendation: str
    screened_at: str

class CandidateDeleteResponse(BaseModel):
    message: str
    candidate_id: int
    deleted_results_count: int

class JobDeleteResponse(BaseModel):
    message: str
    job_id: int
    deleted_results_count: int
    deleted_orphan_candidates_count: int
