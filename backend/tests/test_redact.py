from datetime import date

from app.redact import redact

PATIENT = {"first_name": "Danielle", "last_name": "Johnson", "dob": date(1955, 10, 20), "phone": "555-0142"}


def test_known_values_are_masked_everywhere():
    out = redact("Thanks Danielle, I found Johnson, born October 20, 1955, phone 555-0142.", PATIENT)
    for secret in ("Danielle", "Johnson", "1955", "555-0142"):
        assert secret not in out


def test_spoken_date_of_birth_and_name_intro_are_masked_without_a_known_patient():
    out = redact("Hi, my name is Priya Sharma, born November nineteen ninety five.")
    assert "Priya" not in out and "Sharma" not in out and "nineteen" not in out


def test_phone_and_long_numbers_are_masked():
    out = redact("Call me on (212) 555-0199 or 2125550199, member 123456789.")
    assert not any(ch.isdigit() for ch in out)


def test_appointment_times_and_visit_dates_survive():
    text = "Friday November 13 at 9:00 AM with Dr. Omar Reyes, and your last visit was September 11, 2026."
    assert redact(text, PATIENT) == text


def test_empty_text_passes_through():
    assert redact(None) is None
    assert redact("") == ""
