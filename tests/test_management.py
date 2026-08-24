import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.database import get_database
from app.main import app
from app.routes.management import delete_candidate, delete_job
from app.schemas.results import ScreeningDetailResponse
from app.schemas.screening import ScreeningResult
from app.services.openrouter_client import OpenRouterError


class ManagementEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "test.db"
        self.database_path_patch = patch(
            "app.database.DATABASE_PATH",
            self.database_path,
        )
        self.database_path_patch.start()
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self.job_id = self._insert_job("Backend Engineer")

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.database_path_patch.stop()
        self.temporary_directory.cleanup()

    def _insert_job(self, title: str) -> int:
        with get_database() as connection:
            cursor = connection.execute(
                """
                INSERT INTO jobs (title, description, structured_data_json)
                VALUES (?, ?, ?)
                """,
                (title, f"Description for {title}", "{}"),
            )
            return cursor.lastrowid

    def _insert_candidate(
        self,
        *,
        name: str = "Asha Rao",
        email: str | None = "asha@example.com",
        phone: str | None = "9876543210",
        candidate_data_json: str | None = None,
        resume_text: str = "Private resume text that must never be returned.",
    ) -> int:
        if candidate_data_json is None:
            candidate_data_json = json.dumps(
                {
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "skills": ["Python", "FastAPI"],
                }
            )

        with get_database() as connection:
            cursor = connection.execute(
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
                    email,
                    phone,
                    "asha-resume.txt",
                    resume_text,
                    candidate_data_json,
                ),
            )
            return cursor.lastrowid

    def _insert_result(
        self,
        *,
        job_id: int | None = None,
        candidate_id: int | None = None,
        details_json: str | None = None,
    ) -> tuple[int, int]:
        if job_id is None:
            job_id = self.job_id
        if candidate_id is None:
            candidate_id = self._insert_candidate()
        if details_json is None:
            details_json = json.dumps(
                {
                    "matched_skills": [" Python ", 42, "FastAPI"],
                    "missing_required_skills": ["Docker"],
                    "evidence": [" Built REST APIs. "],
                }
            )

        with get_database() as connection:
            cursor = connection.execute(
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
                    25,
                    8,
                    20,
                    12,
                    15,
                    80,
                    details_json,
                    "The stored evidence supports the score.",
                    "Strong Match",
                ),
            )
            return candidate_id, cursor.lastrowid

    def _count(self, table: str, where: str = "", parameters: tuple = ()) -> int:
        allowed_tables = {"jobs", "candidates", "screening_results"}
        if table not in allowed_tables:
            raise ValueError("Unexpected test table")

        query = f"SELECT COUNT(*) FROM {table}"
        if where:
            query += f" WHERE {where}"

        with get_database() as connection:
            return connection.execute(query, parameters).fetchone()[0]

    def _get_result_row(self, result_id: int):
        with get_database() as connection:
            return connection.execute(
                """
                SELECT
                    required_skills_score,
                    preferred_skills_score,
                    experience_score,
                    education_score,
                    project_relevance_score,
                    total_score,
                    details_json,
                    justification,
                    recommendation
                FROM screening_results
                WHERE id = ?
                """,
                (result_id,),
            ).fetchone()

    def _new_screening_result(self) -> ScreeningResult:
        return ScreeningResult(
            required_skills_score=30,
            preferred_skills_score=10,
            experience_score=25,
            education_score=15,
            project_relevance_score=20,
            total_score=100,
            matched_skills=["Python", "FastAPI", "SQLite"],
            missing_required_skills=[],
            evidence=["Built production APIs."],
            justification="The updated assessment supports every score.",
            recommendation="Strong Match",
        )

    def test_retrieving_existing_screening_result(self) -> None:
        candidate_id = self._insert_candidate(email=None, phone=None)
        _, result_id = self._insert_result(candidate_id=candidate_id)

        response = self.client.get(f"/api/screening-results/{result_id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        validated = ScreeningDetailResponse.model_validate(body)
        self.assertEqual(validated.screening_result_id, result_id)
        self.assertEqual(validated.job.id, self.job_id)
        self.assertEqual(validated.candidate.id, candidate_id)
        self.assertIsNone(validated.candidate.email)
        self.assertIsNone(validated.candidate.phone)
        self.assertEqual(validated.candidate.structured_data["skills"], ["Python", "FastAPI"])
        self.assertEqual(
            validated.scores.model_dump(),
            {
                "required_skills_score": 25,
                "preferred_skills_score": 8,
                "experience_score": 20,
                "education_score": 12,
                "project_relevance_score": 15,
                "total_score": 80,
            },
        )
        self.assertEqual(validated.matched_skills, ["Python", "FastAPI"])
        self.assertEqual(validated.missing_required_skills, ["Docker"])
        self.assertEqual(validated.evidence, ["Built REST APIs."])
        serialized_body = json.dumps(body).lower()
        for forbidden_field in (
            "resume_text",
            "api_key",
            "headers",
            "anonymized_prompt",
            "private resume text",
        ):
            self.assertNotIn(forbidden_field, serialized_body)

    def test_missing_screening_result_returns_404(self) -> None:
        response = self.client.get("/api/screening-results/999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Screening result not found"})

    def test_malformed_candidate_json_returns_empty_dictionary(self) -> None:
        candidate_id = self._insert_candidate(candidate_data_json="{not valid JSON")
        _, result_id = self._insert_result(candidate_id=candidate_id)

        response = self.client.get(f"/api/screening-results/{result_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["candidate"]["structured_data"], {})

    def test_malformed_details_json_returns_empty_lists(self) -> None:
        _, result_id = self._insert_result(details_json="[not an object]")

        response = self.client.get(f"/api/screening-results/{result_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["matched_skills"], [])
        self.assertEqual(response.json()["missing_required_skills"], [])
        self.assertEqual(response.json()["evidence"], [])

    def test_deleting_existing_candidate(self) -> None:
        candidate_id = self._insert_candidate()

        response = self.client.delete(f"/api/candidates/{candidate_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "message": "Candidate deleted successfully.",
                "candidate_id": candidate_id,
                "deleted_results_count": 0,
            },
        )
        self.assertEqual(self._count("candidates", "id = ?", (candidate_id,)), 0)

    def test_missing_candidate_returns_404(self) -> None:
        response = self.client.delete("/api/candidates/999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Candidate not found."})

    def test_candidate_deletion_removes_all_linked_results(self) -> None:
        candidate_id = self._insert_candidate()
        second_job_id = self._insert_job("Platform Engineer")
        self._insert_result(candidate_id=candidate_id)
        self._insert_result(job_id=second_job_id, candidate_id=candidate_id)

        response = self.client.delete(f"/api/candidates/{candidate_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted_results_count"], 2)
        self.assertEqual(
            self._count("screening_results", "candidate_id = ?", (candidate_id,)),
            0,
        )
        self.assertEqual(self._count("candidates", "id = ?", (candidate_id,)), 0)
        self.assertEqual(self._count("jobs"), 2)

    def test_candidate_deletion_rolls_back_if_candidate_delete_fails(self) -> None:
        candidate_id, _ = self._insert_result()
        with get_database() as connection:
            connection.execute(
                f"""
                CREATE TRIGGER block_candidate_delete
                BEFORE DELETE ON candidates
                WHEN OLD.id = {candidate_id}
                BEGIN
                    SELECT RAISE(ABORT, 'blocked candidate deletion');
                END
                """
            )

        with self.assertRaises(sqlite3.IntegrityError):
            delete_candidate(candidate_id)

        self.assertEqual(self._count("candidates", "id = ?", (candidate_id,)), 1)
        self.assertEqual(
            self._count("screening_results", "candidate_id = ?", (candidate_id,)),
            1,
        )

    def test_deleting_existing_job_with_no_candidates(self) -> None:
        response = self.client.delete(f"/api/jobs/{self.job_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "message": "Job deleted successfully.",
                "job_id": self.job_id,
                "deleted_results_count": 0,
                "deleted_orphan_candidates_count": 0,
            },
        )
        self.assertEqual(self._count("jobs", "id = ?", (self.job_id,)), 0)

    def test_missing_job_delete_returns_404(self) -> None:
        response = self.client.delete("/api/jobs/999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Job not found"})

    def test_job_deletion_removes_linked_screening_results(self) -> None:
        first_candidate_id, _ = self._insert_result()
        second_candidate_id = self._insert_candidate(name="Ravi Shah")
        self._insert_result(candidate_id=second_candidate_id)

        response = self.client.delete(f"/api/jobs/{self.job_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted_results_count"], 2)
        self.assertEqual(self._count("screening_results", "job_id = ?", (self.job_id,)), 0)
        self.assertEqual(self._count("jobs", "id = ?", (self.job_id,)), 0)
        self.assertEqual(
            self._count(
                "candidates",
                "id IN (?, ?)",
                (first_candidate_id, second_candidate_id),
            ),
            0,
        )

    def test_job_deletion_removes_orphan_candidates(self) -> None:
        candidate_id, _ = self._insert_result()

        response = self.client.delete(f"/api/jobs/{self.job_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted_orphan_candidates_count"], 1)
        self.assertEqual(self._count("candidates", "id = ?", (candidate_id,)), 0)

    def test_job_deletion_preserves_candidate_linked_to_another_job(self) -> None:
        candidate_id, _ = self._insert_result()
        second_job_id = self._insert_job("Platform Engineer")
        self._insert_result(job_id=second_job_id, candidate_id=candidate_id)

        response = self.client.delete(f"/api/jobs/{self.job_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted_results_count"], 1)
        self.assertEqual(response.json()["deleted_orphan_candidates_count"], 0)
        self.assertEqual(self._count("candidates", "id = ?", (candidate_id,)), 1)
        self.assertEqual(
            self._count(
                "screening_results",
                "job_id = ? AND candidate_id = ?",
                (second_job_id, candidate_id),
            ),
            1,
        )

    def test_job_deletion_rolls_back_if_job_delete_fails(self) -> None:
        candidate_id, _ = self._insert_result()
        with get_database() as connection:
            connection.execute(
                f"""
                CREATE TRIGGER block_job_delete
                BEFORE DELETE ON jobs
                WHEN OLD.id = {self.job_id}
                BEGIN
                    SELECT RAISE(ABORT, 'blocked job deletion');
                END
                """
            )

        with self.assertRaises(sqlite3.IntegrityError):
            delete_job(self.job_id)

        self.assertEqual(self._count("jobs", "id = ?", (self.job_id,)), 1)
        self.assertEqual(self._count("candidates", "id = ?", (candidate_id,)), 1)
        self.assertEqual(self._count("screening_results", "job_id = ?", (self.job_id,)), 1)

    def test_foreign_keys_are_enabled_for_every_managed_connection(self) -> None:
        with get_database() as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO screening_results (job_id, candidate_id)
                    VALUES (?, ?)
                    """,
                    (999, 999),
                )

        self.assertEqual(self._count("screening_results"), 0)

    def test_successful_rescreening_uses_stored_data_and_returns_detail(self) -> None:
        raw_resume = (
            "Asha Rao\n"
            "asha@example.com\n"
            "+91 9876543210\n"
            "PRIVATE_RAW_MARKER\n"
            "SKILLS: Python, FastAPI"
        )
        candidate_id = self._insert_candidate(resume_text=raw_resume)
        _, result_id = self._insert_result(candidate_id=candidate_id)

        with patch(
            "app.routes.management.screen_candidate",
            new=AsyncMock(return_value=self._new_screening_result()),
        ) as mocked_screen_candidate:
            response = self.client.post(
                f"/api/screening-results/{result_id}/rescreen"
            )

        self.assertEqual(response.status_code, 200)
        validated = ScreeningDetailResponse.model_validate(response.json())
        self.assertEqual(validated.screening_result_id, result_id)
        self.assertEqual(validated.candidate.id, candidate_id)
        call_arguments = mocked_screen_candidate.await_args.kwargs
        self.assertEqual(
            call_arguments["job_description"],
            (
                "Job title: Backend Engineer\n\n"
                "Job description:\nDescription for Backend Engineer"
            ),
        )
        anonymized_resume = call_arguments["anonymized_resume"]
        self.assertIn("PRIVATE_RAW_MARKER", anonymized_resume)
        self.assertIn("SKILLS: Python, FastAPI", anonymized_resume)
        self.assertNotIn("Asha Rao", anonymized_resume)
        self.assertNotIn("asha@example.com", anonymized_resume)
        self.assertNotIn("9876543210", anonymized_resume)
        serialized_response = json.dumps(response.json())
        self.assertNotIn(raw_resume, serialized_response)
        self.assertNotIn("PRIVATE_RAW_MARKER", serialized_response)
        self.assertNotIn("resume_text", response.json())

    def test_missing_rescreening_result_returns_404_without_model_call(self) -> None:
        with patch(
            "app.routes.management.screen_candidate",
            new=AsyncMock(),
        ) as mocked_screen_candidate:
            response = self.client.post(
                "/api/screening-results/999/rescreen"
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Screening result not found."})
        mocked_screen_candidate.assert_not_awaited()

    def test_openrouter_failure_returns_502(self) -> None:
        _, result_id = self._insert_result()

        with patch(
            "app.routes.management.screen_candidate",
            new=AsyncMock(side_effect=OpenRouterError("Model unavailable")),
        ):
            response = self.client.post(
                f"/api/screening-results/{result_id}/rescreen"
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"detail": "Model unavailable"})

    def test_openrouter_failure_preserves_previous_result(self) -> None:
        _, result_id = self._insert_result()
        before = dict(self._get_result_row(result_id))

        with patch(
            "app.routes.management.screen_candidate",
            new=AsyncMock(side_effect=OpenRouterError("Request failed")),
        ):
            response = self.client.post(
                f"/api/screening-results/{result_id}/rescreen"
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(dict(self._get_result_row(result_id)), before)

    def test_invalid_model_output_preserves_previous_result(self) -> None:
        _, result_id = self._insert_result()
        before = dict(self._get_result_row(result_id))
        invalid_result = {
            "required_skills_score": 31,
            "preferred_skills_score": 10,
            "experience_score": 25,
            "education_score": 15,
            "project_relevance_score": 20,
        }

        with patch(
            "app.routes.management.screen_candidate",
            new=AsyncMock(return_value=invalid_result),
        ):
            response = self.client.post(
                f"/api/screening-results/{result_id}/rescreen"
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json(),
            {"detail": "OpenRouter returned an invalid screening assessment."},
        )
        self.assertEqual(dict(self._get_result_row(result_id)), before)

    def test_rescreening_updates_all_scores_and_calculates_outcome_locally(self) -> None:
        _, result_id = self._insert_result()
        service_data = self._new_screening_result().model_dump()
        service_data["total_score"] = 1
        service_data["recommendation"] = "Not Recommended"

        with patch(
            "app.routes.management.screen_candidate",
            new=AsyncMock(return_value=service_data),
        ):
            response = self.client.post(
                f"/api/screening-results/{result_id}/rescreen"
            )

        self.assertEqual(response.status_code, 200)
        expected_scores = {
            "required_skills_score": 30,
            "preferred_skills_score": 10,
            "experience_score": 25,
            "education_score": 15,
            "project_relevance_score": 20,
            "total_score": 100,
        }
        self.assertEqual(response.json()["scores"], expected_scores)
        stored = self._get_result_row(result_id)
        for field_name, expected_value in expected_scores.items():
            self.assertEqual(stored[field_name], expected_value)
        self.assertEqual(stored["recommendation"], "Strong Match")

    def test_rescreening_updates_details_justification_and_recommendation(self) -> None:
        _, result_id = self._insert_result()
        new_result = ScreeningResult(
            required_skills_score=20,
            preferred_skills_score=5,
            experience_score=15,
            education_score=10,
            project_relevance_score=10,
            total_score=60,
            matched_skills=["Python"],
            missing_required_skills=["Docker", "Kubernetes"],
            evidence=["Maintained a Python API."],
            justification="The candidate meets some requirements.",
            recommendation="Potential Match",
        )

        with patch(
            "app.routes.management.screen_candidate",
            new=AsyncMock(return_value=new_result),
        ):
            response = self.client.post(
                f"/api/screening-results/{result_id}/rescreen"
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["matched_skills"], ["Python"])
        self.assertEqual(body["missing_required_skills"], ["Docker", "Kubernetes"])
        self.assertEqual(body["evidence"], ["Maintained a Python API."])
        self.assertEqual(body["justification"], "The candidate meets some requirements.")
        self.assertEqual(body["recommendation"], "Potential Match")
        stored = self._get_result_row(result_id)
        self.assertEqual(
            json.loads(stored["details_json"]),
            {
                "matched_skills": ["Python"],
                "missing_required_skills": ["Docker", "Kubernetes"],
                "evidence": ["Maintained a Python API."],
            },
        )
        self.assertEqual(stored["justification"], body["justification"])
        self.assertEqual(stored["recommendation"], body["recommendation"])

    def test_rescreening_does_not_insert_result_or_candidate(self) -> None:
        _, result_id = self._insert_result()
        candidate_count = self._count("candidates")
        result_count = self._count("screening_results")

        with patch(
            "app.routes.management.screen_candidate",
            new=AsyncMock(return_value=self._new_screening_result()),
        ):
            response = self.client.post(
                f"/api/screening-results/{result_id}/rescreen"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._count("candidates"), candidate_count)
        self.assertEqual(self._count("screening_results"), result_count)
        self.assertEqual(response.json()["screening_result_id"], result_id)

    def test_ranking_order_reflects_rescreened_score(self) -> None:
        first_candidate_id, first_result_id = self._insert_result()
        second_candidate_id = self._insert_candidate(name="Ravi Shah")
        _, second_result_id = self._insert_result(candidate_id=second_candidate_id)
        with get_database() as connection:
            connection.execute(
                "UPDATE screening_results SET total_score = ? WHERE id = ?",
                (90, second_result_id),
            )

        before = self.client.get(f"/api/jobs/{self.job_id}/results").json()
        self.assertEqual(before["results"][0]["candidate_id"], second_candidate_id)

        with patch(
            "app.routes.management.screen_candidate",
            new=AsyncMock(return_value=self._new_screening_result()),
        ):
            response = self.client.post(
                f"/api/screening-results/{first_result_id}/rescreen"
            )

        self.assertEqual(response.status_code, 200)
        after = self.client.get(f"/api/jobs/{self.job_id}/results").json()
        self.assertEqual(after["results"][0]["candidate_id"], first_candidate_id)
        self.assertEqual(after["results"][0]["scores"]["total_score"], 100)

    def test_model_call_occurs_before_database_update(self) -> None:
        _, result_id = self._insert_result()

        async def inspect_existing_result(**_: str) -> ScreeningResult:
            self.assertEqual(self._get_result_row(result_id)["total_score"], 80)
            return self._new_screening_result()

        with patch(
            "app.routes.management.screen_candidate",
            new=AsyncMock(side_effect=inspect_existing_result),
        ):
            response = self.client.post(
                f"/api/screening-results/{result_id}/rescreen"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._get_result_row(result_id)["total_score"], 100)

    def test_failed_database_update_rolls_back_existing_result(self) -> None:
        _, result_id = self._insert_result()
        before = dict(self._get_result_row(result_id))
        with get_database() as connection:
            connection.execute(
                f"""
                CREATE TRIGGER block_result_update
                BEFORE UPDATE ON screening_results
                WHEN OLD.id = {result_id}
                BEGIN
                    SELECT RAISE(ABORT, 'blocked result update');
                END
                """
            )

        with patch(
            "app.routes.management.screen_candidate",
            new=AsyncMock(return_value=self._new_screening_result()),
        ):
            with self.assertRaises(sqlite3.IntegrityError):
                self.client.post(
                    f"/api/screening-results/{result_id}/rescreen"
                )

        self.assertEqual(dict(self._get_result_row(result_id)), before)

    def test_existing_ranking_and_screening_routes_remain_functional(self) -> None:
        self._insert_result()

        ranking_response = self.client.get(f"/api/jobs/{self.job_id}/results")

        self.assertEqual(ranking_response.status_code, 200)
        self.assertEqual(ranking_response.json()["candidate_count"], 1)

        mocked_result = ScreeningResult(
            required_skills_score=25,
            preferred_skills_score=8,
            experience_score=20,
            education_score=12,
            project_relevance_score=15,
            total_score=80,
            matched_skills=["Python", "FastAPI"],
            missing_required_skills=[],
            evidence=["Built REST APIs."],
            justification="The resume supports the score.",
            recommendation="Strong Match",
        )
        resume = b"Asha Rao\nasha@example.com\nSKILLS\nPython, FastAPI"
        with patch(
            "app.routes.screening.screen_candidate",
            new=AsyncMock(return_value=mocked_result),
        ) as mocked_screen_candidate:
            screening_response = self.client.post(
                f"/api/jobs/{self.job_id}/screen",
                files={"files": ("resume.txt", resume, "text/plain")},
            )

        self.assertEqual(screening_response.status_code, 200)
        self.assertEqual(screening_response.json()["successful_count"], 1)
        mocked_screen_candidate.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
