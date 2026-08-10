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


def _library_error_for(token: str) -> Exception:
    """The exception the REAL firebase_admin raises for `token`.

    Not a hand-written stand-in. `_token_gen.TokenVerifier._decode_unverified`
    (firebase_admin/_token_gen.py:411) is exactly these two calls, an
    `except ValueError`, and a re-raise as `InvalidIdTokenError(str(error))`
    with the message preserved. Reproducing it here rather than inventing a
    message is the whole point: the first version of the test below asserted
    that a token was absent from a message its own author had written, so it
    could not fail for the reason it existed.

    Pure parsing — no app, no network, no certs.
    """
    from firebase_admin import auth as firebase_auth
    from google.auth import jwt

    try:
        jwt.decode_header(token)
        jwt.decode(token, verify=False)
    except ValueError as error:
        return firebase_auth.InvalidIdTokenError(str(error), cause=error)
    raise AssertionError(f"{token!r} parsed cleanly; it was chosen because it cannot")


def test_the_library_really_does_echo_the_bearer_bytes_into_its_message():
    """Pins the upstream behaviour the redaction below exists for.

    If a future firebase_admin or google-auth stops formatting the token into
    the message, this fails and the redaction can be reconsidered on evidence
    instead of left in place forever guarding nothing. If it keeps doing it,
    the next test is testing something real.
    """
    secret = "supersecret-not-a-jwt"
    exc = _library_error_for(secret)
    assert type(exc).__name__ == "InvalidIdTokenError"
    assert secret in str(exc)


def test_a_rejected_token_is_logged_by_type_without_its_bytes(caplog):
    """The refusal has to leave a trace on the server, and only the type of one.

    An intermittent 401 on a cold `GET /api/rooms` sat in the ledger for three
    tasks explained by a theory that turned out to be wrong, and it stayed
    un-diagnosable because this path discarded the exception entirely.

    The exception raised here is the one the real library raises for these
    bytes, so the assertion below can actually fail: before the redaction it
    would have found `supersecret-not-a-jwt` in the record.
    """
    secret = "supersecret-not-a-jwt"
    with (
        caplog.at_level("WARNING", logger="star.auth"),
        mock.patch("star.auth._verify", side_effect=_library_error_for(secret)),
    ):
        assert verify_token(f"Bearer {secret}") is None

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "InvalidIdTokenError" in message
    # `extract_bearer` waves through any two whitespace-separated parts, so
    # these bytes are the caller's choice. They do not reach the operator's log.
    assert secret not in message
    assert "Wrong number of segments" not in message


def test_a_cert_fetch_failure_keeps_its_message(caplog):
    """The one message worth having, and the one that cannot carry the token.

    `_token_gen.py:405` builds CertificateFetchError from a TransportError
    raised while fetching the certs URL, so it describes our own HTTP failure.
    It is also the leading suspect for the 401 this log was added to diagnose,
    so redacting everything would have thrown away the answer along with the
    risk.
    """
    from firebase_admin import auth as firebase_auth

    boom = firebase_auth.CertificateFetchError(
        "Could not fetch certificates at https://www.googleapis.com/…: timed out",
        cause=TimeoutError(),
    )
    with (
        caplog.at_level("WARNING", logger="star.auth"),
        mock.patch("star.auth._verify", side_effect=boom),
    ):
        assert verify_token("Bearer a.b.c") is None

    message = caplog.records[0].getMessage()
    assert "CertificateFetchError" in message
    assert "timed out" in message


def test_a_logged_message_is_bounded_and_single_line(caplog):
    """Even the trusted message is stripped and capped.

    A public endpoint that writes an unbounded, caller-influenced string into
    the operator's log at WARNING is an amplifier, and a newline in one is log
    forging. Neither is reachable through CertificateFetchError today; both are
    one upstream wording change away, and the guard costs a line.
    """
    from firebase_admin import auth as firebase_auth

    boom = firebase_auth.CertificateFetchError(
        "x" * 5000 + "\nWARNING:star.auth:uid=admin verified", cause=TimeoutError()
    )
    with (
        caplog.at_level("WARNING", logger="star.auth"),
        mock.patch("star.auth._verify", side_effect=boom),
    ):
        assert verify_token("Bearer a.b.c") is None

    message = caplog.records[0].getMessage()
    assert "\n" not in message
    assert "uid=admin verified" not in message
    assert len(message) < 300


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
