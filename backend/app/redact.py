"""Best-effort masking of personal details in call transcripts shown on the dashboard.

Known values (the verified patient's name, birth date, phone) are masked exactly. Patterns and phrases catch the
rest: phone numbers, birth-year dates, spoken dates of birth, "my name is X". Appointment times and visit dates are
left alone because staff need them to check what the agent promised. This is best effort: a name nobody
introduced, or one the speech-to-text garbled, can slip through, so never describe the output as anonymised.
"""

import re
from datetime import date

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_NUMBER_WORDS = (
    "zero|oh|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    "seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|first|second|third|"
    "fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|"
    "seventeenth|eighteenth|nineteenth|twentieth|thirtieth"
)
_FLAGS = re.IGNORECASE
# "October 20, 1955" and "October 20th 1955": a birth-year-looking date (1900-2019); 2020+ stays, as a visit date
_WRITTEN_DOB = re.compile(rf"\b(?:{MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+(?:19\d\d|20[01]\d)\b", _FLAGS)
# "November nineteen ninety five": a month followed by two or more number words
_SPOKEN_DOB = re.compile(rf"\b(?:{MONTHS})(?:[\s,-]+(?:{_NUMBER_WORDS})\b){{2,8}}", _FLAGS)
_NUMERIC_DATE = re.compile(r"\b\d{1,2}/\d{1,2}/(?:19|20)\d\d\b|\b(?:19|20)\d\d-\d{2}-\d{2}\b")
_PHONE = re.compile(r"\(?\b\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b|\b\d{3}[-.\s]\d{4}\b")
_LONG_DIGITS = re.compile(r"\b\d{7,}\b")
_NAME_INTRO = re.compile(r"\b(my name is|my name's|this is|i am|i'm|it's|name is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)")


def _known_patterns(patient: dict) -> list[tuple[re.Pattern, str]]:
    out = []
    for key in ("first_name", "last_name"):
        if patient.get(key):
            out.append((re.compile(rf"\b{re.escape(patient[key])}\b", _FLAGS), "[NAME]"))
    dob: date | None = patient.get("dob")
    if dob:
        month = dob.strftime("%B")
        out.append(
            (re.compile(rf"\b{month}\s+0?{dob.day}(?:st|nd|rd|th)?,?\s+{dob.year}\b", _FLAGS), "[DOB]"),
        )
    if patient.get("phone"):
        digits = re.sub(r"\D", "", patient["phone"])
        out.append((re.compile(r"[-.\s]?".join(re.escape(d) for d in digits)), "[PHONE]"))
    return out


def redact(text: str | None, patient: dict | None = None) -> str | None:
    """Mask personal details in one turn's text. `patient` is the verified patient, if the call had one."""
    if not text:
        return text
    for pattern, label in _known_patterns(patient or {}):
        text = pattern.sub(label, text)
    text = _WRITTEN_DOB.sub("[DOB]", text)
    text = _SPOKEN_DOB.sub("[DOB]", text)
    text = _NUMERIC_DATE.sub("[DOB]", text)
    text = _PHONE.sub("[PHONE]", text)
    text = _LONG_DIGITS.sub("[NUMBER]", text)
    return _NAME_INTRO.sub(lambda m: f"{m.group(1)} [NAME]", text)
