import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIRECTORY = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIRECTORY / "resume_screener.db"

@contextmanager
def get_database() -> Generator[sqlite3.Connection, None, None]:
    '''
    Provide a database connection and close it automatcally.

    The transaction is committed when the operation succeeds and rolled back when an exception occurs.
    '''
    DATA_DIRECTORY.mkdir(parents=True,exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
    finally:
        connection.close()

def initialize_database() -> None:

    with get_database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL DEFAULT 'Unknown Candidate',
                email TEXT,
                phone TEXT,
                resume_filename TEXT NOT NULL,
                resume_text TEXT NOT NULL,
                structured_data_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS screening_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                candidate_id INTEGER NOT NULL,

                required_skills_score INTEGER NOT NULL DEFAULT 0,
                preferred_skills_score INTEGER NOT NULL DEFAULT 0,
                experience_skills_score INTEGER NOT NULL DEFAULT 0,
                education_skills_score INTEGER NOT NULL DEFAULT 0,
                project_relevance_score INTEGER NOT NULL DEFAULT 0,
                total_score INTEGER NOT NULL DEFAULT 0,

                details_json TEXT NOT NULL DEFAULT '{}',
                justification TEXT NOT NULL DEFAULT '',
                recommedation TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (job_id)
                    REFERENCES jobs(id)
                    ON DELETE CASCADE,
                
                FOREIGN KEY (candidate_id)
                    REFERENCES candidates(id)
                    ON DELETE CASCADE,
                
                UNIQUE(job_id, candidate_id)
            );

            CREATE INDEX IF NOT EXISTS idx_results_jobs_id
                ON screening_results(job_id);
            
            CREATE INDEX IF NOT EXISTS idx_results_candidate_id
                ON screening_results(candidate_id);
            """
        )


def database_is_available() -> bool:
    try:
        with get_database() as connection:
            connection.execute("SELECT 1").fetchone()
        return True
    except sqlite3.Error:
        return False