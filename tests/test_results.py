import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import get_database
from app.main import app
from app.schemas.results import JobRankingResponse


class RankedResultsEndpointTests(unittest.TestCase):
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
                ("Backend Engineer", "Build backend APIs.", "{}"),
            )
            self.job_id = cursor.lastrowid

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.database_path_patch.stop()
        self.temporary_directory.cleanup()

    def _insert_candidate_result(
        self,
        *,
        name: str,
        total_score: int,
        required_skills_score: int,
        experience_score: int,
        created_at: str,
        candidate_data_json: str | None = None,
        details_json: str | None = None,
    ) -> tuple[int, int]:
        if candidate_data_json is None:
            candidate_data_json = json.dumps(
                {"skills": ["Python", "FastAPI"]}
            )
        if details_json is None:
            details_json = json.dumps(
                {
                    "matched_skills": ["Python"],
                    "missing_required_skills": ["Docker"],
                    "evidence": ["Built APIs"],
                }
            )

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
                    name,
                    f"{name.lower().replace(' ', '.')}@example.com",
                    "1234567890",
                    f"{name.lower().replace(' ', '-')}.txt",
                    "Private resume text that must not be returned.",
                    candidate_data_json,
                ),
            )
            candidate_id = candidate_cursor.lastrowid
            result_cursor = connection.execute(
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
                    recommendation,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.job_id,
                    candidate_id,
                    required_skills_score,
                    5,
                    experience_score,
                    10,
                    10,
                    total_score,
                    details_json,
                    "Supported by the stored evidence.",
                    "Potential Match",
                    created_at,
                ),
            )

        return candidate_id, result_cursor.lastrowid

    def test_existing_job_returns_multiple_ranked_candidates(self) -> None:
        lower_candidate_id, _ = self._insert_candidate_result(
            name="Lower Score",
            total_score=70,
            required_skills_score=25,
            experience_score=20,
            created_at="2026-08-24 10:00:00",
        )
        higher_candidate_id, _ = self._insert_candidate_result(
            name="Higher Score",
            total_score=90,
            required_skills_score=28,
            experience_score=22,
            created_at="2026-08-24 11:00:00",
        )

        response = self.client.get(f"/api/jobs/{self.job_id}/results")

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertEqual(response_data["candidate_count"], 2)
        self.assertEqual(
            [result["candidate_id"] for result in response_data["results"]],
            [higher_candidate_id, lower_candidate_id],
        )
        self.assertEqual(
            [result["rank"] for result in response_data["results"]],
            [1, 2],
        )

    def test_existing_job_with_zero_candidates_returns_empty_results(self) -> None:
        response = self.client.get(f"/api/jobs/{self.job_id}/results")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "job_id": self.job_id,
                "job_title": "Backend Engineer",
                "candidate_count": 0,
                "results": [],
            },
        )

    def test_missing_job_returns_404(self) -> None:
        response = self.client.get("/api/jobs/999/results")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "job not found."})

    def test_ranking_uses_every_tie_breaker_in_order(self) -> None:
        inserted = []
        for name, total, required, experience, screened_at in (
            ("Lower Total", 89, 30, 25, "2026-08-24 08:00:00"),
            ("Lower Required", 90, 28, 25, "2026-08-24 08:00:00"),
            ("Lower Experience", 90, 29, 20, "2026-08-24 08:00:00"),
            ("Later Screening", 90, 29, 21, "2026-08-24 10:00:00"),
            ("First ID", 90, 29, 21, "2026-08-24 09:00:00"),
            ("Second ID", 90, 29, 21, "2026-08-24 09:00:00"),
        ):
            candidate_id, _ = self._insert_candidate_result(
                name=name,
                total_score=total,
                required_skills_score=required,
                experience_score=experience,
                created_at=screened_at,
            )
            inserted.append(candidate_id)

        response = self.client.get(f"/api/jobs/{self.job_id}/results")

        self.assertEqual(response.status_code, 200)
        ranked_ids = [
            result["candidate_id"] for result in response.json()["results"]
        ]
        self.assertEqual(
            ranked_ids,
            [inserted[4], inserted[5], inserted[3], inserted[2], inserted[1], inserted[0]],
        )

    def test_invalid_candidate_data_json_returns_empty_skills(self) -> None:
        self._insert_candidate_result(
            name="Invalid Candidate JSON",
            total_score=75,
            required_skills_score=25,
            experience_score=20,
            created_at="2026-08-24 10:00:00",
            candidate_data_json="{not valid JSON",
        )

        response = self.client.get(f"/api/jobs/{self.job_id}/results")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["skills"], [])

    def test_invalid_details_json_returns_empty_detail_lists(self) -> None:
        self._insert_candidate_result(
            name="Invalid Details JSON",
            total_score=75,
            required_skills_score=25,
            experience_score=20,
            created_at="2026-08-24 10:00:00",
            details_json="[not an object]",
        )

        response = self.client.get(f"/api/jobs/{self.job_id}/results")

        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual(result["matched_skills"], [])
        self.assertEqual(result["missing_required_skills"], [])
        self.assertEqual(result["evidence"], [])

    def test_response_fields_match_job_ranking_response(self) -> None:
        self._insert_candidate_result(
            name="Schema Candidate",
            total_score=75,
            required_skills_score=25,
            experience_score=20,
            created_at="2026-08-24 10:00:00",
            candidate_data_json=json.dumps(
                {"skills": [" Python ", 123, "", None, "FastAPI"]}
            ),
            details_json=json.dumps(
                {
                    "matched_skills": [" Python ", 123],
                    "missing_required_skills": "Docker",
                    "evidence": [None, " Built APIs "],
                }
            ),
        )

        response = self.client.get(f"/api/jobs/{self.job_id}/results")

        self.assertEqual(response.status_code, 200)
        validated = JobRankingResponse.model_validate(response.json())
        result = validated.results[0]
        self.assertIsInstance(validated.candidate_count, int)
        self.assertEqual(result.skills, ["Python", "FastAPI"])
        self.assertEqual(result.matched_skills, ["Python"])
        self.assertEqual(result.missing_required_skills, [])
        self.assertEqual(result.evidence, ["Built APIs"])
        self.assertNotIn("resume_text", response.json()["results"][0])


if __name__ == "__main__":
    unittest.main()
