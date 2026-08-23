import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.database import get_database, initialize_database
from app.main import app
from app.routes.jobs import _row_to_job_response
from app.schemas.jobs import JobRequirements
from app.services.job_extractor import (
    _clean_json_response,
    _normalize_job_requirements,
)
from app.services.openrouter_client import OpenRouterError


JOB_DESCRIPTION = (
    "Build and maintain Python APIs with FastAPI and SQLite. "
    "The engineer must write tests and review backend code."
)


def sample_requirements() -> JobRequirements:
    return JobRequirements(
        job_summary="Build and maintain backend APIs.",
        required_skills=["Python", "FastAPI"],
        preferred_skills=["SQLite"],
        education_requirements=[],
        experience_requirements=["Two years of backend experience"],
        responsibilities=["Build APIs", "Review code"],
        keywords=["Python", "backend"],
    )


class JobApiTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.database_path_patch.stop()
        self.temporary_directory.cleanup()

    def test_job_response_conversion(self) -> None:
        requirements = sample_requirements()

        with get_database() as connection:
            cursor = connection.execute(
                """
                INSERT INTO jobs (title, description, structured_data_json)
                VALUES (?, ?, ?)
                """,
                (
                    "Backend Engineer",
                    JOB_DESCRIPTION,
                    requirements.model_dump_json(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM jobs WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()

        response = _row_to_job_response(row)

        self.assertEqual(response.title, "Backend Engineer")
        self.assertEqual(response.structured_data, requirements)
        self.assertIsInstance(response.created_at, str)

    def test_empty_job_listing_returns_empty_list(self) -> None:
        response = self.client.get("/api/jobs")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_missing_job_returns_404(self) -> None:
        response = self.client.get("/api/jobs/999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Job not found."})

    def test_successful_job_creation_with_mocked_openrouter_result(self) -> None:
        requirements = sample_requirements()
        model_data = requirements.model_dump()
        model_data["job_title"] = "Backend Engineer"

        class MockOpenRouterResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    "```json\n"
                                    f"{json.dumps(model_data)}\n"
                                    "```"
                                )
                            }
                        }
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
                payload = kwargs["json"]
                self_test.assertNotIn("provider", payload)
                self_test.assertNotIn("response_format", payload)
                return MockOpenRouterResponse()

        self_test = self

        with patch.dict(
            os.environ,
            {"OPENROUTER_API_KEY": "test-api-key"},
        ), patch(
            "app.services.job_extractor.httpx.AsyncClient",
            MockAsyncClient,
        ):
            response = self.client.post(
                "/api/jobs",
                json={
                    "title": "Backend Engineer",
                    "description": JOB_DESCRIPTION,
                },
            )

        self.assertEqual(response.status_code, 201)
        response_data = response.json()
        self.assertEqual(response_data["title"], "Backend Engineer")
        self.assertEqual(
            response_data["structured_data"],
            requirements.model_dump(),
        )
        self.assertIn("created_at", response_data)

        list_response = self.client.get("/api/jobs")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

        get_response = self.client.get(
            f"/api/jobs/{response_data['id']}"
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json(), response_data)

    def test_openrouter_failure_returns_502(self) -> None:
        with patch(
            "app.routes.jobs.extract_job_requirements",
            new=AsyncMock(side_effect=OpenRouterError("Model unavailable")),
        ):
            response = self.client.post(
                "/api/jobs",
                json={
                    "title": "Backend Engineer",
                    "description": JOB_DESCRIPTION,
                },
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"detail": "Model unavailable"})


class JobNormalizationTests(unittest.TestCase):
    def test_openrouter_response_normalization(self) -> None:
        model_content = """
        Here is the extracted result:
        ```json
        {
          "job_title": "Backend Engineer",
          "job_summary": null,
          "required_skills": " Python ",
          "preferred_skills": null,
          "experience_requirements": ["2 years", "2 years", 3],
          "responsibilities": [" Build APIs ", ""],
          "metadata": {"source": "model"}
        }
        ```
        """

        cleaned_content = _clean_json_response(model_content)
        extracted_data = json.loads(cleaned_content)
        normalized_data = _normalize_job_requirements(extracted_data)
        requirements = JobRequirements.model_validate(normalized_data)

        self.assertEqual(requirements.job_summary, "")
        self.assertEqual(requirements.required_skills, ["Python"])
        self.assertEqual(requirements.preferred_skills, [])
        self.assertEqual(requirements.education_requirements, [])
        self.assertEqual(
            requirements.experience_requirements,
            ["2 years"],
        )
        self.assertEqual(requirements.responsibilities, ["Build APIs"])
        self.assertEqual(requirements.keywords, [])
        self.assertNotIn("job_title", requirements.model_dump())


class DatabaseMigrationTests(unittest.TestCase):
    def test_existing_jobs_table_is_migrated_without_data_loss(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "legacy.db"
            connection = sqlite3.connect(database_path)
            connection.execute(
                """
                CREATE TABLE jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "INSERT INTO jobs (title, description) VALUES (?, ?)",
                ("Legacy Job", JOB_DESCRIPTION),
            )
            connection.commit()
            connection.close()

            with patch("app.database.DATABASE_PATH", database_path):
                initialize_database()

                with get_database() as migrated_connection:
                    columns = migrated_connection.execute(
                        "PRAGMA table_info(jobs)"
                    ).fetchall()
                    row = migrated_connection.execute(
                        """
                        SELECT title, description, structured_data_json
                        FROM jobs
                        WHERE id = ?
                        """,
                        (1,),
                    ).fetchone()

            self.assertIn(
                "structured_data_json",
                {column["name"] for column in columns},
            )
            self.assertEqual(row["title"], "Legacy Job")
            self.assertEqual(row["description"], JOB_DESCRIPTION)
            self.assertEqual(row["structured_data_json"], "{}")


if __name__ == "__main__":
    unittest.main()
