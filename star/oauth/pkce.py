"""PKCE, and only S256.

What PKCE is for, in one sentence, because the rest of this file is a
consequence of it: an authorization code travels back through a redirect, and
a redirect is a channel a native client shares with every other program on the
laptop. Whoever intercepts the code still cannot exchange it without the
verifier, which never left the client that made it.

`plain` is refused outright rather than being supported and discouraged. Under
`plain` the challenge IS the verifier, so anyone who saw the authorization
request can complete the exchange, which is the attack the mechanism exists to
stop. OAuth 2.1 removes it; star/oauth/metadata.py advertises `S256` alone; a
client that asks for `plain` here is told no rather than quietly downgraded.

Pure. No clock, no store, no network — the whole module is one hash and one
comparison, which is what makes the accept case and every refusal testable as
values.
"""

import base64
import hashlib
import hmac
import string

METHOD = "S256"

# RFC 7636's ABNF for both the verifier and the challenge: 43 to 128 characters
# from the unreserved set. The floor is the interesting one — 43 base64url
# characters is 256 bits, which is the point of the whole exercise, and a
# verifier a client generated from four digits would pass a hash comparison
# just as happily as a real one. This is where that is refused.
MIN_LENGTH = 43
MAX_LENGTH = 128
_UNRESERVED = frozenset(string.ascii_letters + string.digits + "-._~")


def challenge_for(verifier: str) -> str:
    """`BASE64URL(SHA256(ASCII(verifier)))`, unpadded.

    Unpadded because RFC 7636 says so, and the `=` a padded encoder appends is
    not a character the challenge's own ABNF admits — a padded challenge would
    fail `is_valid_challenge` below and, worse, would silently fail to match a
    correctly-encoded client's value. `b64encode` plus a translate is the
    stdlib's only unpadded base64url, and 32 bytes always produces exactly one
    unit of padding, so this strips a known quantity rather than guessing.
    """
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _well_formed(value: object) -> bool:
    return (
        isinstance(value, str)
        and MIN_LENGTH <= len(value) <= MAX_LENGTH
        and set(value) <= _UNRESERVED
    )


def is_valid_verifier(verifier: object) -> bool:
    """Is this a code verifier at all? Checked before it is ever hashed."""
    return _well_formed(verifier)


def is_valid_challenge(challenge: object) -> bool:
    """Is this a code challenge at all? Checked at `/authorize`, not at exchange.

    Refusing a malformed challenge when it is REGISTERED rather than when it is
    verified is the half that matters: a challenge nobody can produce a
    verifier for turns into a code that cannot be redeemed, and the client
    finds out one round trip and one consent screen later, with no way to tell
    that from a server fault.
    """
    return _well_formed(challenge)


def verify(verifier: object, challenge: object, method: object = METHOD) -> bool:
    """Does this verifier produce this challenge under S256?

    Four ways to be false and only one to be true. The method is checked first
    and against `S256` exactly — not case-insensitively, because RFC 7636
    defines the value as `S256` and a server that also accepts `s256` is a
    server whose behaviour depends on a client's casing. `None` and an absent
    method reach here as something that is not `S256` and are refused, which
    is the correct reading: OAuth's default for an absent method is `plain`,
    and `plain` is not offered.

    `hmac.compare_digest` on the derived challenge, matching star/tokens.py's
    hash comparison and for the same reason — this is a comparison against a
    value derived from a secret, and its timing should not describe the secret.
    The mismatch is unlikely to be exploitable across a network on 43 ASCII
    characters, and it costs one function name to not have to argue about that.
    """
    if method != METHOD:
        return False
    if not is_valid_verifier(verifier) or not is_valid_challenge(challenge):
        return False
    return hmac.compare_digest(challenge_for(verifier), challenge)
