import unittest

from app.services.pii_redactor import redact_personal_information
from app.services.resume_parser import extract_resume_data

SAMPLE_RESUME = """
Arjun Kumar
arjun.kumar@example.com
+91 9876543210

EDUCATION
Bachelor of Technology in Computer Science
ABC University, 2022-2026

SKILLS
Python, FastAPI, Flask, SQL, MySQL, Git, HTML, CSS, JavaScript

EXPERIENCE
Backend Development Intern, Example Technologies
January 2025 - June 2025

Developed REST APIs using Python and FastAPI.
Designed MySQL database tables and optimized SQL queries.
Used Git and GitHub for collaborative development.

PROJECTS
Online Vehicle Rental System
Developed a Flask and MySQL application for managing vehicles,
customers, bookings and payments.
"""

class ResumeParserTests(unittest.TestCase):

    def test_extracts_candidate_information(self):
        result = extract_resume_data(SAMPLE_RESUME)

        self.assertEqual(result["name"],"Arjun Kumar")
        self.assertEqual(
            result["email"],
            "arjun.kumar@example.com"
        )
        self.assertIn("9876543210",result["phone"])

    def test_extracts_known_skills(self):
        result = extract_resume_data(SAMPLE_RESUME)

        self.assertIn("Python", result["skills"])
        self.assertIn("FastAPI", result["skills"])
        self.assertIn("Flask", result["skills"])
        self.assertIn("SQL", result["skills"])
        self.assertIn("MySQL", result["skills"])
        self.assertIn("Git", result["skills"])
        self.assertIn("GitHub", result["skills"])

    def test_extracts_resume_sections(self):
        result = extract_resume_data(SAMPLE_RESUME)

        self.assertIn("Bachelor of Technology", result["education"])
        self.assertIn("Backend Development Intern", result["experience"])
        self.assertIn("Vehicle Rental System",result["projects"])

    def test_extracts_content_after_inline_section_heading(self):
        result = extract_resume_data(
            "Asha Rao\nSKILLS: Python, FastAPI\nPROJECTS: Resume Screener"
        )

        self.assertEqual(result["projects"], "Resume Screener")

    def test_redacts_personal_information(self):
        result = extract_resume_data(SAMPLE_RESUME)

        anonymized = redact_personal_information(
            text = SAMPLE_RESUME,
            name = result["name"],
            email = result["email"],
            phone = result["phone"],
        )

        self.assertNotIn("Arjun Kumar", anonymized)
        self.assertNotIn("arjun.kumar@example.com",anonymized)
        self.assertNotIn("9876543210", anonymized)

        self.assertIn("[REDACTED_NAME]", anonymized)
        self.assertIn("[REDACTED_EMAIL]", anonymized)
        self.assertIn("[REDACTED_PHONE]", anonymized)

        # Academic years must not be mistaken for phone numbers.
        self.assertIn("2022-2026", anonymized)

if __name__ == "__main__":
    unittest.main()
