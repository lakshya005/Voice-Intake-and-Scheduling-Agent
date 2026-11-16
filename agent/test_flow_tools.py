from flow_tools import parse_dob, red_flag, spoken, visit_spoken


def test_red_flag_catches_phrases_and_curly_apostrophes():
    assert red_flag("I have chest pain since morning") == "chest pain"
    assert red_flag("I can’t breathe properly") == "can't breathe"
    assert red_flag("a sore throat for three days") is None


def test_spoken_uses_clinic_time():
    # 19:30 UTC on Oct 26 is 3:30 PM in New York (EDT)
    assert (
        spoken("2026-10-26T19:30:00+00:00", "Dr. Maya Chen")
        == "Monday October 26 at 3:30 PM with Dr. Maya Chen"
    )


def test_visit_spoken_has_no_leading_zero():
    assert visit_spoken("2026-09-05") == "September 5, 2026"


def test_parse_dob_accepts_spoken_and_numeric_styles():
    for text in (
        "January 1, 1990",
        "january 1st 1990",
        "Jan 1, 1990",
        "1/1/1990",
        "1990-01-01",
        "1 January 1990",
    ):
        assert parse_dob(text) == "1990-01-01", text


def test_parse_dob_rejects_non_dates():
    assert parse_dob("February 30, 1990") is None
    assert parse_dob("nineteen ninety") is None
