import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

MAX_FILE_SIZE = 5*1024*1024
SUPPORTED_EXTENSIONS = {".pdf",".txt"}

class FileParsingError(ValueError):
    """Raised when an uploaded resume cannot be processed."""

@dataclass(frozen=True)
class ParsedResumeFile:
    """Strucutured result returned after extracting a resume file."""
    filename: str
    file_type: str
    text: str
    character_count: int
    page_count: int

def clean_extracted_text(text: str) -> str:
    """Remove unnecessary spacing and control characters."""
    text = text.replace("\x00","")
    text = text.replace("\r\n","\n").replace("\r","\n")
    
    text = re.sub(r"[ \t]+"," ",text)
    text = re.sub(r"\n{3,}","\n\n",text)

    return text.strip()

def extract_pdf_text(file_content: bytes) -> tuple[str, int]:
    '''Extract text and page count from a PDF file.'''
    if not file_content.startswith(b"%PDF"):
        raise FileParsingError(
            "The upload file has a .pdf extension but is not a valid PDF."
        )
    try:
        reader = PdfReader(BytesIO(file_content))
    except Exception as error:
        raise FileParsingError(
            "The PDF is damaged or cannot be opened."
        ) from error

    if reader.is_encrypted:
        raise FileParsingError(
            "Password-protected PDF files are not supported."
        )

    page_texts: list[str] = []

    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
            if page_text.strip():
                page_texts.append(page_text)
        except Exception:
            " Continue processing when only one page cannot be read."
            continue

    extracted_text = clean_extracted_text("\n\n".join(page_texts))

    if not extracted_text:
        raise FileParsingError(
            "No readable text was found. the PDF may be screened or image_based."
        )

    return extracted_text,len(reader.pages)

def extract_txt_text(file_content: bytes) -> str:
    """ Decode text from a TXT resume. """
    try:
        text = file_content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = file_content.decode('latin-1')
        except UnicodeDecodeError as error:
            raise FileParsingError(
                "The TXT file uses as unsupported character encoding."
            ) from error
    
    extracted_text = clean_extracted_text(text)
    if not extracted_text:
        raise FileParsingError(
            "The TXT file is empty."
        )

    return extracted_text

def parse_resume_file(original_filename: str, file_content: bytes)-> ParsedResumeFile:
    '''Validate and extract text from a PDF or TXT resume.'''
    safe_filename = Path(original_filename).name
    extension = Path(safe_filename).suffix.lower()

    if not safe_filename:
        raise FileParsingError(
            "The uploaded file has no filename."
        )

    if extension not in SUPPORTED_EXTENSIONS:
        raise FileParsingError(
            "Unsupported file format. Upload only PDF or TXT files."
        )

    if not file_content:
        raise FileParsingError(
            "The uploaded file is empty."
        )

    if len(file_content)>MAX_FILE_SIZE:
        raise FileParsingError(
            "The file exceeds the maximum permitted size of 5MB."
        )
    if extension==".pdf":
        extracted_text, page_count = extract_pdf_text(file_content)
    else:
        extracted_text = extract_txt_text(file_content)
        page_count = 1
    
    return ParsedResumeFile(
        filename = safe_filename,
        file_type = extension.removeprefix("."),
        text=extracted_text,
        character_count=len(extracted_text),
        page_count=page_count,
    )