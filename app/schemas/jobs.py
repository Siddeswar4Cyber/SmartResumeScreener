from pydantic import BaseModel, ConfigDict, Field


class JobCreateRequest(BaseModel):
    """Data entered by the recruiter."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    title: str = Field(
        min_length=2,
        max_length=200,
    )

    description: str = Field(
        min_length=50,
        max_length=20_000,
    )


class JobRequirements(BaseModel):
    """Structured requirements extracted from the raw job description."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    job_summary: str = ""
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)
    experience_requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class JobResponse(BaseModel):
    """Job information returned by the API."""

    id: int
    title: str
    description: str
    structured_data: JobRequirements
    created_at: str
