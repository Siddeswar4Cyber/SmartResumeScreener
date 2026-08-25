import json
import os

import httpx
from dotenv import load_dotenv
from pydantic import ValidationError

from app.schemas.jobs import JobRequirements
from app.schemas.screening import (ScreeningAssessment, ScreeningResult)

from app.services.job_extractor import JOB_EXTRACTION_SYSTEM_PROMPT
from app.services.llm_errors import LLMError
from app.services.openrouter_client import (MAX_JOB_DESCRIPTION_LENGTH, MAX_RESUME_LENGTH, SYSTEM_PROMPT, parse_screening_response)


load_dotenv()
OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://127.0.0.1:11434",
).rstrip("/")

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen3.5:4b",
)

OLLAMA_TIMEOUT_SECONDS = float(
    os.getenv("OLLAMA_TIMEOUT_SECONDS","300")
)

OLLAMA_NUM_CTX = int(
    os.getenv("OLLAMA_NUM_CTX","8192")
)

class OllamaError(LLMError):
    """Raised when ollama cannot produce a valid results."""

def _extract_ollama_error(response: httpx.Response)->str:
    '''Extract a safe Ollama error message.'''
    try:
        response_data = response.json()
        message = response_data.get("error")

        if message:
            return str(message)
    except ValueError:
        pass

    return response.text[:500] or "Unknown Ollama error"

async def _ollama_chat(messages: list[dict[str, str]], output_schema: dict,) -> str:
    '''Send a structured-output request to local Ollama.'''
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "format": output_schema,
        "options": {
            "temperature": 0,
            "num_ctx": OLLAMA_NUM_CTX,
        },
        "keep_alive": "10m",
    }

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{OLLAMA_BASE_URL}/api/chat",json=payload,)

            response.raise_for_status()
    except httpx.HTTPStatusError as error:
        message = _extract_ollama_error(error.response)

        raise OllamaError(
            f"Ollama request failed "
            f"({error.response.status_code}): {message}"
        ) from error

    except httpx.RequestError as error:
        raise OllamaError(
            "could not connect to ollama. ensure the ollama application is running."
        ) from error

    except httpx.TimeoutException as error:
        raise OllamaError(
            "Ollama did not respond before the timeout. "
        ) from error

    try:
        response_data = response.json()
        content = response_data["message"]["content"]

    except (ValueError, TypeError, KeyError) as error:
        raise OllamaError(
            "Ollama returned as unexpected response."
        ) from error

    if not isinstance(content, str) or not content.strip():
        raise OllamaError(
            "Ollama returned empty model content."
        )

    return content.strip()

def _normalize_list(value: object)->list[str]:
    '''Normalize a model value into a string list.'''
    if value is None:
        return []

    if isinstance(value, str):
        value = value.strip()
        return [value] if value else []

    if not isinstance(value, list):
        return []

    normalized = [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]

    return list(dict.fromkeys(normalized))

async def extract_job_requirements(
        title:str,
        description: str,
) -> JobRequirements:
    """Extract job requirements using local Ollama."""

    title = title.strip()
    description = description.strip()

    if not title:
        raise OllamaError("the job title is empty.")

    if not description:
        raise OllamaError("the description is empty.")

    if len(description)> MAX_JOB_DESCRIPTION_LENGTH:
        raise OllamaError(
            "The job description exceeds 20,000 characters."
        )

    content = await _ollama_chat(
        messages=[
            {
                "role": "system",
                "content": JOB_EXTRACTION_SYSTEM_PROMPT,
            },
            {
                "role" : "user",
                "content": (
                    "<job_title>\n"
                    f"{title}\n"
                    "</job_title>\n\n"
                    "<job_description>\n"
                    f"{description}\n"
                    "</job_description>"
                ),
            },
        ],
        output_schema=(
            JobRequirements.model_json_schema()
        ),
    )

    try:
        extracted_data = json.loads(content)

    except json.JSONDecodeError as error:
        raise OllamaError(
            "Ollama returned invalid job JSON."
        ) from error

    if not isinstance(extracted_data, dict):
        raise OllamaError(
            "Ollama job output must be a JSON object."
        )

    extracted_data.pop("job_title", None)

    normalized_data = {
        "job_summary": str(extracted_data.get("job_summary") or "").strip(),
        "required_skills": list(extracted_data.get("required_skills") or []),
        "preferred_skills": list(extracted_data.get("preferred_skills") or []),
        "education_requirements" : list(extracted_data.get("education_requirements") or []),
        "experience_requirements": list(extracted_data.get("experience_requirements") or []),
        "responsibilities": _normalize_list(extracted_data.get("responsibilities") or []),
        "keywords": _normalize_list(extracted_data.get("keywords")),
    }
    print(json.dumps(normalized_data,indent=2))

    try:
        return JobRequirements.model_validate(normalized_data)

    except ValueError as error:
        raise OllamaError(
            "Ollama job output did not match the required schema"
        ) from error

async def screen_candidate(job_description: str, anonymized_resume: str,) -> ScreeningResult:
    """Screen one candidate using local Ollama."""

    job_description = job_description.strip()
    anonymized_resume = anonymized_resume.strip()

    if not job_description:
        raise OllamaError(
            "The job description is empty."
        )

    if len(job_description)>MAX_JOB_DESCRIPTION_LENGTH:
        raise OllamaError(
            "the job description exceeds 20,000 characters."
        )

    if len(anonymized_resume) > MAX_RESUME_LENGTH:
        raise OllamaError(
            "the resume exceeds 50,000 characters."
        )

    content = await _ollama_chat(
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": (
                    "Evaluate the following anonymized candidate. \n\n"
                    "<job_description>\n"
                    f"{job_description}\n"
                    "</job_description>\n\n"
                    "<anonymized_resume>\n"
                    f"{anonymized_resume}\n"
                    "</anonymized_resume>"
                ),
            },
        ],
        output_schema=(
            ScreeningAssessment.model_json_schema()
        ),
    )

    try:
        return parse_screening_response(content)

    except LLMError:
        raise 

    except Exception as error:
        raise OllamaError(
            "Ollama screening output could not be validated"
        ) from error