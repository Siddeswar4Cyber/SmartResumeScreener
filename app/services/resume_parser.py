import re
from typing import Optional

EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
URL_PATTERN = re.compile(
    r"https?://|www\.", re.IGNORECASE
)

NAME_WORD_PATTERN = re.compile(
    r"^[A-Z][A-Za-z.'-]*$"
)

PHONE_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:\+?\d{1,3}[\s.-]?)?"
    r"(?:\(?\d{3,5}\)?[\s.-]?)?"
    r"\d{3,5}[\s.-]?\d{4}"
    r"(?!\d)"
)

SKILL_PATTERNS: dict[str, list[str]] = {
    "Python": ["python"],
    "Java": ["java"],
    "C": ["c"],
    "C++": ["c++"],
    "C#": ["c#"],
    "JavaScript": ["javascript", "java script"],
    "TypeScript": ["typescript", "type script"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3"],
    "SQL": ["sql"],
    "MySQL": ["mysql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MongoDB": ["mongodb", "mongo db"],
    "SQLite": ["sqlite"],
    "FastAPI": ["fastapi", "fast api"],
    "Flask": ["flask"],
    "Django": ["django"],
    "Spring Boot": ["spring boot"],
    "Node.js": ["node.js", "nodejs"],
    "Express.js": ["express.js", "expressjs"],
    "React": ["react", "react.js", "reactjs"],
    "Angular": ["angular"],
    "Vue.js": ["vue.js", "vuejs"],
    "REST API": ["rest api", "restful api", "restful services"],
    "GraphQL": ["graphql"],
    "Git": ["git"],
    "GitHub": ["github"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Linux": ["linux"],
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure", "microsoft azure"],
    "Google Cloud": ["gcp", "google cloud platform"],
    "PyTorch": ["pytorch"],
    "TensorFlow": ["tensorflow"],
    "Scikit-learn": ["scikit-learn", "sklearn"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "OpenCV": ["opencv"],
    "Machine Learning": ["machine learning"],
    "Deep Learning": ["deep learning"],
    "Natural Language Processing": [
        "natural language processing",
        "nlp",
    ],
    "Large Language Models": [
        "large language model",
        "large language models",
        "llm",
        "llms",
    ],
    "Data Structures": ["data structures", "dsa"],
    "Algorithms": ["algorithms"],
    "Object-Oriented Programming": [
        "object-oriented programming",
        "object oriented programming",
        "oops",
        "oop",
    ],
    "Cybersecurity": ["cybersecurity", "cyber security"],
    "Network Security": ["network security"],
    "Penetration Testing": ["penetration testing", "pen testing"],
    "SIEM": ["siem"],
    "Suricata": ["suricata"],
    "Zeek": ["zeek"],
    "Wireshark": ["wireshark"],
}

SECTION_HEADINGS: dict[str, str] = {
    "EDUCATION": "education",
    "ACADEMIC BACKGROUND": "education",
    "ACADEMIC QUALIFICATIONS": "education",
    "QUALIFICATIONS": "education",

    "EXPERIENCE": "experience",
    "WORK EXPERIENCE": "experience",
    "PROFESSIONAL EXPERIENCE": "experience",
    "EMPLOYMENT HISTORY": "experience",
    "INTERNSHIPS": "experience",
    "INTERNSHIP": "experience",

    "SKILLS": "skills_section",
    "TECHNICAL SKILLS": "skills_section",
    "CORE SKILLS": "skills_section",
    "TECHNOLOGIES": "skills_section",

    "PROJECTS": "projects",
    "ACADEMIC PROJECTS": "projects",
    "PERSONAL PROJECTS": "projects",
    "KEY PROJECTS": "projects",

    "CERTIFICATIONS": "certifications",
    "CERTIFICATES": "certifications",
    "LICENSES AND CERTIFICATIONS": "certifications",
}


NAME_BLOCKLIST = {
    "resume",
    "curriculum vitae",
    "cv",
    "profile",
    "professional profile",
    "summary",
    "professional summary",
    "career objective",
    "objective",
    "contact",
    "contact information",
    "personal information",
    "address",
    "email",
    "phone",
}

TITLE_KEYWORDS = {
    "engineer", "developer", "manager", "consultant", "analyst",
    "designer", "specialist", "director", "intern", "architect",
    "scientist", "administrator", "coordinator", "executive", "lead",
    "officer", "founder", "president", "recruiter", "accountant",
    "programmer", "technician", "supervisor", "strategist",
}

def normalize_heading(text: str) -> str:
    """ Normalize a line so it can be compared with section headings."""
    normalized = text.upper().strip()
    normalized = re.sub(r"[^A-Z]"," ",normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()

def extract_email(text: str) -> Optional[str]:
    '''Return the first email address found in the resume.'''

    match = EMAIL_PATTERN.search(text)
    return match.group(0) if match else None

def extract_phone(text: str) -> Optional[str]:
    '''Return the first email address found in the resume'''
    for match in PHONE_PATTERN.finditer(text):
        phone = match.group(0).strip()
        digit_count = len(re.sub(r"\D","",phone))

        if 10<= digit_count <= 15:
            return phone
    return None


def extract_name(text:str) -> str:
    """
    Estimate the candidate name from the first few lines.

    This is a heuristic because resumes do not follow one fixed format.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    best_single_word = None

    for line in lines[:10]:
        candidates = [line.strip(" |•-")]

        if re.search(r"[|•]", line):
            candidates += [s.strip(" -") for s in re.split(r"[|•]", line) if s.strip()]

        for candidate in candidates:
            if not candidate:
                continue

            candidate_lower = candidate.lower()

            if EMAIL_PATTERN.search(candidate):
                continue

            if PHONE_PATTERN.search(candidate):
                continue

            if URL_PATTERN.search(candidate):
                continue

            if any(character.isdigit() for character in candidate):
                continue
            if "http://" in candidate_lower or "https://" in candidate_lower:
                continue

            if "linkedin" in candidate_lower or "github" in candidate_lower:
                continue

            if candidate_lower in NAME_BLOCKLIST:
                continue

            if normalize_heading(candidate) in SECTION_HEADINGS:
                continue

            words = candidate.split()
            
            if any(w.strip(".,").lower() in TITLE_KEYWORDS for w in words):
                continue

            if candidate.isupper():
                pass
            else:
                if not all(NAME_WORD_PATTERN.match(w) for w in words):
                    continue
            if len(words)==1:
                best_single_word = candidate
            if not 2 <= len(words) <=5:
                continue
            
            if not 3<=len(candidate)<=60:
                continue

            return candidate

    return best_single_word or "Unknown Candidate"

def extract_skills(text: str) -> list[str]:
    '''Find known technical Skills explicity mentioneed in the resume.'''
    detected_skills: list[str] = []

    for canonical_name, aliases in SKILL_PATTERNS.items():
        for alias in aliases:
            pattern = (
                rf"(?<![A-Za-z0-9])"
                rf"{re.escape(alias)}"
                rf"(?![A-Za-z0-9])"
            )

            if re.search(pattern, text, flags=re.IGNORECASE):
                detected_skills.append(canonical_name)
                break
    return detected_skills

def extract_sections(text: str)-> dict[str,str]:
    '''Extract common resume sections using their headings.'''
    sections: dict[str, list[str]] = {
        "education": [],
        "experience": [],
        "skills_section": [],
        "projects": [],
        "certifications": [],
    }

    current_section: Optional[str] = None

    for original_line in text.splitlines():
        line = original_line.strip()

        if not line:
            continue
        normalized_line = normalize_heading(line)

        if normalized_line in SECTION_HEADINGS:
            current_section = SECTION_HEADINGS[normalized_line]
            continue

        if ":" in line:
            possible_heading, remaining_text = line.split(":", 1)
            normalized_heading = normalize_heading(possible_heading)

            if normalized_heading in SECTION_HEADINGS:
                current_section = SECTION_HEADINGS[normalized_heading]

                if remaining_text.strip():
                    sections[current_section].append(remaining_text.strip())

                continue

        if current_section:
            sections[current_section].append(line)

    return {
        section_name: "\n".join(lines).strip()
        for section_name, lines in sections.items()
    }

def extract_resume_data(text: str)->dict:
    '''Convert extracted resume text into structured information.'''
    sections = extract_sections(text)

    return {
        "name": extract_name(text),
        "email": extract_email(text),
        "phone": extract_phone(text),
        "skills": extract_skills(text),
        "education":sections["education"],
        "experience": sections["experience"],
        "projects": sections["projects"],
        "certifications": sections["certifications"],
    }
