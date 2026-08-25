import os

from dotenv import load_dotenv

from app.schemas.jobs import JobRequirements
from app.schemas.screening import ScreeningResult
from app.services.job_extractor import extract_job_requirements as openrouter_extract_job
from app.services.openrouter_client import screen_candidate as openrouter_screen_candidate

from app.services.llm_errors import LLMError
from app.services.ollama_client import extract_job_requirements as ollama_extract_job
from app.services.ollama_client import screen_candidate as ollama_screen_candidate

load_dotenv()

def get_llm_provider() -> str:
    return os.getenv("LLM_PROVIDER","ollama").strip().lower()

async def extract_job_requirements(title: str, description: str) -> JobRequirements:
    """Extract a JD using the configured provider."""
    provider = get_llm_provider()

    if provider == "ollama":
        return await ollama_extract_job(title=title, description=description)

    if provider == "openrouter":
        return await openrouter_extract_job(title=title, description=description)

    raise LLMError(
        f"Unsupported LLM_PROVIDER: {provider}"
    )


async def screen_candidate(job_description: str, anonymized_resume: str) -> ScreeningResult:
    provider = get_llm_provider()

    if provider=="ollama":
        return await ollama_screen_candidate(
            job_description=job_description,
            anonymized_resume=anonymized_resume,
        )

    if provider=="openrouter":
        return await openrouter_extract_job(
            job_description=job_description,
            anonymized_resume=anonymized_resume,
        )

    raise LLMError(
        f"Unsupported LLM_PROVIDER: {provider}"
    )

