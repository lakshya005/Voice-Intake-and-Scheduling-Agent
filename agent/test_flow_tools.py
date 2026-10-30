from flow_tools import red_flag, spoken


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
