import re
from typing import Optional

from app.services.resume_parser import EMAIL_PATTERN, PHONE_PATTERN

def _redact_valid_phone(match: re.Match) -> str:
    '''
    Redact a match only when it contains enough digits to be a realistic phone number.

    This prevents year ranges such as 2022-2026 from beign removed
    '''

    matched_text = match.group(0)
    digit_count = len(re.sub(r"\D","", matched_text))

    if 10<= digit_count <= 15:
        return "[REDACTED_PHONE]"
    return matched_text

def redact_personal_information(
        text: str,
        name: Optional[str],
        email: Optional[str],
        phone: Optional[str],
)-> str:
    """
    Remove basic personal identifiers before sending resume text to the scoring model.
    """
    redacted_text = text

    redacted_text = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", redacted_text)
    redacted_text = PHONE_PATTERN.sub(_redact_valid_phone, redacted_text)

    if name and name!="Unknown Candidate":
        redacted_text = re.sub(
            re.escape(name),
            "[REDACTED_NAME]",
            redacted_text,
            flags=re.IGNORECASE,
        )

    if email:
        redacted_text = redacted_text.replace(email,"[REDACTED_EMAIL]")

    if phone:
        redacted_text = redacted_text.replace(phone,"[REDACTED_PHONE]")

    return redacted_text