from evals.ledger import PROMISE


def test_promise_matches_booked_claims_only():
    assert PROMISE.search("Your appointment is booked for Friday")
    assert PROMISE.search("You're all booked")
    assert not PROMISE.search("Would you like me to get that booked?")
    assert not PROMISE.search("Your appointment is not booked yet")


def test_visit_date_pattern_ignores_appointment_times():
    from evals.ledger import VISIT_DATE

    assert VISIT_DATE.findall(
        "Your last visit was September 11, 2026 with Dr. Nair"
    ) == ["September 11, 2026"]
    assert not VISIT_DATE.findall("Friday November 13 at 9:00 AM with Dr. Reyes")
