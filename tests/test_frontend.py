import tempfile
import unittest
import re
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.routes.frontend import FRONTEND_DIRECTORY
from app.schemas.jobs import JobRequirements


class DashboardHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements_by_id: dict[str, str] = {}
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.elements_by_id[element_id] = tag
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"])


class FrontendEndpointTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.database_path_patch.stop()
        self.temporary_directory.cleanup()

    def test_dashboard_returns_200(self) -> None:
        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)

    def test_dashboard_returns_html(self) -> None:
        response = self.client.get("/dashboard")

        self.assertTrue(response.headers["content-type"].startswith("text/html"))
        self.assertIn("<!DOCTYPE html>", response.text)

    def test_stylesheet_is_served_from_static_mount(self) -> None:
        response = self.client.get("/static/styles.css")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/css", response.headers["content-type"])

    def test_javascript_is_served_from_static_mount(self) -> None:
        response = self.client.get("/static/app.js")

        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers["content-type"])

    def test_root_docs_and_job_listing_remain_accessible(self) -> None:
        root_response = self.client.get("/")
        docs_response = self.client.get("/docs")
        jobs_response = self.client.get("/api/jobs")

        self.assertEqual(root_response.status_code, 200)
        self.assertEqual(docs_response.status_code, 200)
        self.assertEqual(jobs_response.status_code, 200)
        self.assertEqual(jobs_response.json(), [])

    def test_job_creation_api_remains_accessible_without_real_model_call(self) -> None:
        requirements = JobRequirements(
            job_summary="Build and maintain backend APIs.",
            required_skills=["Python", "FastAPI"],
        )
        with patch(
            "app.routes.jobs.extract_job_requirements",
            new=AsyncMock(return_value=requirements),
        ) as mocked_extractor:
            response = self.client.post(
                "/api/jobs",
                json={
                    "title": "Backend Engineer",
                    "description": (
                        "Build and maintain Python APIs with FastAPI, SQLite, "
                        "automated tests, and code review responsibilities."
                    ),
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["title"], "Backend Engineer")
        mocked_extractor.assert_awaited_once()

    def test_missing_dashboard_file_returns_controlled_404(self) -> None:
        missing_path = Path(self.temporary_directory.name) / "missing-index.html"

        with patch("app.routes.frontend.DASHBOARD_PATH", missing_path):
            response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {"detail": "Dashboard frontend is unavailable."},
        )

    def test_dashboard_contains_required_controls_and_static_links(self) -> None:
        response = self.client.get("/dashboard")
        parser = DashboardHTMLParser()
        parser.feed(response.text)

        self.assertEqual(parser.elements_by_id["job-form"], "form")
        self.assertEqual(parser.elements_by_id["job-title"], "input")
        self.assertEqual(parser.elements_by_id["job-description"], "textarea")
        self.assertEqual(parser.elements_by_id["create-job-button"], "button")
        self.assertEqual(parser.elements_by_id["refresh-jobs-button"], "button")
        self.assertEqual(parser.elements_by_id["jobs-list"], "div")
        self.assertEqual(parser.elements_by_id["job-details"], "div")
        self.assertEqual(parser.elements_by_id["job-search"], "input")
        self.assertEqual(parser.elements_by_id["resume-files"], "input")
        self.assertEqual(parser.elements_by_id["screen-resumes-button"], "button")
        self.assertEqual(parser.elements_by_id["results-list"], "div")
        self.assertEqual(parser.elements_by_id["candidate-modal"], "div")
        self.assertEqual(parser.elements_by_id["rescreen-candidate-button"], "button")
        self.assertEqual(parser.elements_by_id["delete-candidate-button"], "button")
        self.assertIn("/docs", parser.links)
        self.assertIn('href="/static/styles.css"', response.text)
        self.assertIn('src="/static/app.js"', response.text)

    def test_all_javascript_id_selectors_exist_in_dashboard_html(self) -> None:
        html = (FRONTEND_DIRECTORY / "index.html").read_text(encoding="utf-8")
        javascript = (FRONTEND_DIRECTORY / "app.js").read_text(encoding="utf-8")
        parser = DashboardHTMLParser()
        parser.feed(html)

        selected_ids = set(
            re.findall(r'document\.querySelector\("#([A-Za-z0-9_-]+)"\)', javascript)
        )

        self.assertTrue(selected_ids)
        self.assertEqual(selected_ids - parser.elements_by_id.keys(), set())

    def test_frontend_does_not_contain_unsafe_or_private_browser_content(self) -> None:
        combined = "\n".join(
            (FRONTEND_DIRECTORY / filename).read_text(encoding="utf-8")
            for filename in ("index.html", "styles.css", "app.js")
        ).lower()

        for forbidden in (
            "innerhtml",
            "openrouter.ai",
            "openrouter_api_key",
            "authorization",
            "resume_text",
            "console.log",
        ):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
