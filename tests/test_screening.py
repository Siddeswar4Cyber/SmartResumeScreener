import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.database import get_database
from app.main import app
from app.routes.screening import _save_screening_result
from app.services.openrouter_client import (
    OpenRouterError,
    _extract_json_response,
    parse_screening_response,
    screen_candidate,
)


JOB_DESCRIPTION = (
    "Build Python and FastAPI services backed by SQLite. "
    "Candidates should have API testing experience."
)

TXT_RESUME = """Asha Rao
asha.rao@example.com
+91 9876543210

SKILLS
Python, FastAPI, SQLite, Git

EXPERIENCE
Backend engineer building and testing REST APIs.

EDUCATION
Bachelor of Technology in Computer Science

PROJECTS
Built a resume screening API with FastAPI and SQLite.
"""


def valid_assessment_data() -> dict:
    return {
        "required_skills_score": 25,
        "preferred_skills_score": 8,
        "experience_score": 20,
        "education_score": 12,
        "project_relevance_score": 15,
        "matched_skills": ["Python", "FastAPI", "SQLite"],
        "missing_required_skills": [],
        "evidence": ["Built and tested REST APIs."],
        "justification": "The resume supports most required qualifications.",
    }


class ScreeningResponseTests(unittest.TestCase):
    def test_plain_json(self) -> None:
        content = json.dumps(valid_assessment_data())

        extracted = _extract_json_response(content)
        result = parse_screening_response(content)

        self.assertIsInstance(extracted, dict)
        self.assertEqual(result.total_score, 80)
        self.assertEqual(result.recommendation, "Strong Match")

    def test_json_inside_markdown_fences(self) -> None:
        content = f"```json\n{json.dumps(valid_assessment_data())}\n```"

        result = parse_screening_response(content)

        self.assertEqual(result.required_skills_score, 25)
        self.assertEqual(result.matched_skills, ["Python", "FastAPI", "SQLite"])

    def test_reasoning_text_followed_by_json(self) -> None:
        content = (
            "I compared the evidence with the rubric.\n"
            "An earlier note was {not valid JSON}.\n"
            f"Final assessment: {json.dumps(valid_assessment_data())}"
        )

        result = parse_screening_response(content)

        self.assertEqual(result.total_score, 80)

    def test_model_total_and_recommendation_are_ignored(self) -> None:
        assessment_data = valid_assessment_data()
        assessment_data["total_score"] = 1
        assessment_data["recommendation"] = "Not Recommended"

        result = parse_screening_response(json.dumps(assessment_data))

        self.assertEqual(result.total_score, 80)
        self.assertEqual(result.recommendation, "Strong Match")

    def test_missing_optional_fields_use_safe_defaults(self) -> None:
        assessment_data = {
            key: value
            for key, value in valid_assessment_data().items()
            if key.endswith("_score")
        }

        result = parse_screening_response(json.dumps(assessment_data))

        self.assertEqual(result.matched_skills, [])
        self.assertEqual(result.missing_required_skills, [])
        self.assertEqual(result.evidence, [])
        self.assertEqual(result.justification, "")

    def test_invalid_score_range_is_rejected(self) -> None:
        assessment_data = valid_assessment_data()
        assessment_data["experience_score"] = 26

        with self.assertRaisesRegex(
            OpenRouterError,
            "did not match the screening schema",
        ):
            parse_screening_response(json.dumps(assessment_data))

    def test_all_five_score_fields_are_required(self) -> None:
        assessment_data = valid_assessment_data()
        del assessment_data["education_score"]

        with self.assertRaisesRegex(
            OpenRouterError,
            "did not match the screening schema",
        ):
            parse_screening_response(json.dumps(assessment_data))

    def test_empty_model_content_is_rejected(self) -> None:
        with self.assertRaisesRegex(OpenRouterError, "empty model content"):
            parse_screening_response("   ")

    def test_content_without_json_object_is_rejected(self) -> None:
        with self.assertRaisesRegex(OpenRouterError, "valid JSON object"):
            parse_screening_response("No structured assessment was returned.")


class OpenRouterClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_message_content_without_strict_routing_parameters(self) -> None:
        response_content = json.dumps(valid_assessment_data())
        captured_payload = {}

        class MockOpenRouterResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {
                    "choices": [
                        {"message": {"content": response_content}}
                    ]
                }

        class MockAsyncClient:
            def __init__(self, **_: object) -> None:
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_: object) -> None:
                return None

            async def post(self, _: str, **kwargs: object):
                captured_payload.update(kwargs["json"])
                return MockOpenRouterResponse()

        with patch.dict(
            os.environ,
            {"OPENROUTER_API_KEY": "test-api-key"},
        ), patch(
            "app.services.openrouter_client.httpx.AsyncClient",
            MockAsyncClient,
        ):
            result = await screen_candidate(
                job_description=JOB_DESCRIPTION,
                anonymized_resume="[REDACTED_NAME]\nPython FastAPI SQLite",
            )

        self.assertEqual(result.total_score, 80)
        self.assertNotIn("response_format", captured_payload)
        self.assertNotIn("provider", captured_payload)
        user_prompt = captured_payload["messages"][1]["content"]
        self.assertIn("</job_description>", user_prompt)


class ScreeningEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temporary_directory.name) / "test.db"
        self.database_path_patch = patch(
            "app.database.DATABASE_PATH",
            database_path,
        )
        self.database_path_patch.start()
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

        with get_database() as connection:
            cursor = connection.execute(
                """
                INSERT INTO jobs (title, description, structured_data_json)
                VALUES (?, ?, ?)
                """,
                ("Backend Engineer", JOB_DESCRIPTION, "{}"),
            )
            self.job_id = cursor.lastrowid

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.database_path_patch.stop()
        self.temporary_directory.cleanup()

    def test_successful_single_resume_screening(self) -> None:
        screening_result = parse_screening_response(
            json.dumps(valid_assessment_data())
        )

        with patch(
            "app.routes.screening.screen_candidate",
            new=AsyncMock(return_value=screening_result),
        ) as mocked_screen_candidate:
            response = self.client.post(
                f"/api/jobs/{self.job_id}/screen",
                files={
                    "files": (
                        "asha-resume.txt",
                        TXT_RESUME.encode("utf-8"),
                        "text/plain",
                    )
                },
            )

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertEqual(response_data["successful_count"], 1)
        self.assertEqual(response_data["failed_count"], 0)
        self.assertEqual(response_data["results"][0]["filename"], "asha-resume.txt")
        self.assertEqual(response_data["results"][0]["screening"]["total_score"], 80)

        call_kwargs = mocked_screen_candidate.await_args.kwargs
        self.assertNotIn("Asha Rao", call_kwargs["anonymized_resume"])
        self.assertNotIn("asha.rao@example.com", call_kwargs["anonymized_resume"])
        self.assertIn("</job_description>", (
            f"<job_description>\n{call_kwargs['job_description']}\n"
            "</job_description>"
        ))

        with get_database() as connection:
            candidate = connection.execute(
                """
                SELECT name, email, phone, resume_filename, resume_text,
                       structured_data_json
                FROM candidates
                """
            ).fetchone()
            screening = connection.execute(
                """
                SELECT experience_score, total_score, recommendation
                FROM screening_results
                """
            ).fetchone()

        self.assertEqual(candidate["name"], "Asha Rao")
        self.assertEqual(candidate["email"], "asha.rao@example.com")
        self.assertIn("9876543210", candidate["phone"])
        self.assertEqual(candidate["resume_filename"], "asha-resume.txt")
        self.assertEqual(screening["experience_score"], 20)
        self.assertEqual(screening["total_score"], 80)
        self.assertEqual(screening["recommendation"], "Strong Match")

    def test_failed_openrouter_screening_does_not_insert_partial_records(self) -> None:
        with patch(
            "app.routes.screening.screen_candidate",
            new=AsyncMock(side_effect=OpenRouterError("Model unavailable")),
        ):
            response = self.client.post(
                f"/api/jobs/{self.job_id}/screen",
                files={
                    "files": (
                        "asha-resume.txt",
                        TXT_RESUME.encode("utf-8"),
                        "text/plain",
                    )
                },
            )

        self.assertEqual(response.status_code, 422)
        response_data = response.json()["detail"]
        self.assertEqual(response_data["failed_files"][0]["stage"], "screening")

        with get_database() as connection:
            candidate_count = connection.execute(
                "SELECT COUNT(*) FROM candidates"
            ).fetchone()[0]
            screening_count = connection.execute(
                "SELECT COUNT(*) FROM screening_results"
            ).fetchone()[0]

        self.assertEqual(candidate_count, 0)
        self.assertEqual(screening_count, 0)

    def test_candidate_insert_rolls_back_when_screening_insert_fails(self) -> None:
        screening_result = parse_screening_response(
            json.dumps(valid_assessment_data())
        )

        with self.assertRaises(sqlite3.IntegrityError):
            _save_screening_result(
                job_id=999,
                filename="asha-resume.txt",
                resume_text=TXT_RESUME,
                structured_data={"name": "Asha Rao"},
                screening_result=screening_result,
            )

        with get_database() as connection:
            candidate_count = connection.execute(
                "SELECT COUNT(*) FROM candidates"
            ).fetchone()[0]

        self.assertEqual(candidate_count, 0)


if __name__ == "__main__":
    unittest.main()
