from evals.ledger import PROMISE


def test_promise_matches_booked_claims_only():
    assert PROMISE.search("Your appointment is booked for Friday")
    assert PROMISE.search("You're all booked")
    assert not PROMISE.search("Would you like me to get that booked?")
    assert not PROMISE.search("Your appointment is not booked yet")
