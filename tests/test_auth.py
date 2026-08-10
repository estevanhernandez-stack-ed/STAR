from unittest import mock

from star.auth import extract_bearer, verify_token


def test_extract_bearer_pulls_the_token():
    assert extract_bearer("Bearer abc.def.ghi") == "abc.def.ghi"


def test_extract_bearer_is_case_insensitive_on_the_scheme():
    assert extract_bearer("bearer abc.def.ghi") == "abc.def.ghi"


def test_extract_bearer_tolerates_extra_whitespace():
    assert extract_bearer("  Bearer   abc.def.ghi  ") == "abc.def.ghi"


def test_extract_bearer_rejects_a_missing_header():
    assert extract_bearer(None) is None
    assert extract_bearer("") is None


def test_extract_bearer_rejects_the_wrong_scheme():
    assert extract_bearer("Basic abc.def.ghi") is None
    assert extract_bearer("abc.def.ghi") is None


def test_extract_bearer_rejects_an_empty_credential():
    assert extract_bearer("Bearer ") is None
    assert extract_bearer("Bearer") is None


def test_verify_token_returns_the_uid_on_a_good_token():
    with mock.patch("star.auth._verify", return_value={"uid": "abc123"}):
        assert verify_token("Bearer good.token.here") == "abc123"


def test_verify_token_returns_none_when_firebase_rejects_it():
    with mock.patch("star.auth._verify", side_effect=ValueError("bad signature")):
        assert verify_token("Bearer bad.token.here") is None


def test_a_rejected_token_is_logged_with_its_cause(caplog):
    """The refusal has to leave a trace on the server, and only on the server.

    An intermittent 401 on a cold `GET /api/rooms` sat in the ledger for three
    tasks explained by a theory that turned out to be wrong, and it stayed
    un-diagnosable because this path discarded the exception. The log line is
    the whole fix; this pins that it exists and carries the cause.
    """
    with (
        caplog.at_level("WARNING", logger="star.auth"),
        mock.patch("star.auth._verify", side_effect=ValueError("Could not fetch certs")),
    ):
        assert verify_token("Bearer bad.token.here") is None

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "ValueError" in message
    assert "Could not fetch certs" in message
    # The credential itself must never reach a log line — a bearer token in a
    # log file is a bearer token an operator can replay.
    assert "bad.token.here" not in message


def test_a_missing_or_malformed_header_is_not_logged_as_a_failure(caplog):
    """Every unauthenticated poke at a public endpoint would otherwise write a
    warning, which turns the signal this log exists for into noise."""
    with caplog.at_level("WARNING", logger="star.auth"):
        assert verify_token(None) is None
        assert verify_token("Basic nope") is None
    assert caplog.records == []


def test_verify_token_returns_none_without_calling_firebase_on_a_bad_header():
    """A malformed header must not cost a network round trip."""
    with mock.patch("star.auth._verify") as verifier:
        assert verify_token("Basic nope") is None
        verifier.assert_not_called()


def test_verify_token_returns_none_when_the_claim_set_has_no_uid():
    with mock.patch("star.auth._verify", return_value={}):
        assert verify_token("Bearer good.token.here") is None


def test_verify_token_returns_none_when_the_claim_set_is_not_a_dict():
    """The contract is never-raises, so a surprising return shape is a None,
    not an AttributeError escaping to the caller."""
    for surprising in (None, [], "claims", 42):
        with mock.patch("star.auth._verify", return_value=surprising):
            assert verify_token("Bearer good.token.here") is None
