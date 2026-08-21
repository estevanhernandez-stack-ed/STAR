"""Central configuration (review fix M3).

One place for model choices and limits. For demo week, pin explicit
versioned model IDs via env vars — `-latest` is a floating alias and can
change behavior under a rehearsed demo.
"""

import os

from google.genai.types import ThinkingLevel

# Pinned, not floating. `gemini-flash-latest` is an alias that resolved to
# gemini-3.6-flash on 2026-08-09 — the model both verified room builds ran on.
# Leaving the alias in place means Google can move the model out from under a
# rehearsed demo. Revisit after the 2026-09-07 deadline.
_PINNED_FLASH = "gemini-3.6-flash"


def fast_model() -> str:
    """Extraction/verification steps."""
    return os.environ.get("STAR_FAST_MODEL", _PINNED_FLASH)


def smart_model() -> str:
    """Planning and synthesis steps."""
    return os.environ.get("STAR_SMART_MODEL", _PINNED_FLASH)


def max_searches_per_build() -> int:
    return int(os.environ.get("STAR_MAX_SEARCHES_PER_BUILD", "30"))


def max_treatment_chars() -> int:
    return int(os.environ.get("STAR_MAX_TREATMENT_CHARS", "8000"))


def max_room_title_chars() -> int:
    """Ceiling on a room's name.

    120 because a title is read in a rail column, not in a document: past
    roughly this it stops being a name and starts being a sentence the list
    has to truncate anyway. Unlike the treatment cap this was never measured
    against a cost — nothing downstream is priced by it — so it exists to keep
    the rail legible rather than to bound a spend.
    """
    return int(os.environ.get("STAR_MAX_ROOM_TITLE_CHARS", "120"))


def max_scene_chars() -> int:
    """Ceiling on one pasted scene (Pipeline B).

    8000 to match the treatment cap above, which is roughly four script pages
    at standard formatting — more than any single scene a writer checks in one
    pass. Unlike the treatment cap this number was never measured against a
    real check's cost or latency; it is carried from the treatment cap because
    the two pastes are the same order of size.
    (default — confirm on next interactive run)
    """
    return int(os.environ.get("STAR_MAX_SCENE_CHARS", "8000"))


def max_searches_per_check() -> int:
    """Per-check search budget, seeded into ADK session state.

    A check is not a build. A build researches four categories from nothing
    and gets 30; a check starts from a room that has already been researched
    and only pays for what the room's own files do not answer. Eight live
    searches is generous for one scene, and the ceiling matters more here than
    in a build because a check is synchronous — every search is time a writer
    spends watching a working state.
    """
    return int(os.environ.get("STAR_MAX_SEARCHES_PER_CHECK", "8"))


def max_scenes_per_sweep() -> int:
    """How many scenes one sweep will read.

    A feature is 24 to 60 scenes; a series bible or a stitched-together
    anthology can be far more, and extraction is one model call each. The cap
    is not about money — extraction spends no searches — it is about a single
    request holding a bounded amount of work, so a 400-scene paste is refused
    with an explanation rather than sat on until a timeout.

    Measured against The Beat That Shook The Void, a 27-page special: 24
    scenes, 82 claims raised, 65 distinct.
    """
    return int(os.environ.get("STAR_MAX_SCENES_PER_SWEEP", "80"))


def max_searches_per_sweep() -> int:
    """The one ceiling a whole-draft sweep runs under.

    A check gets 8 for one scene. A sweep gets this for an entire screenplay,
    and that single number is the point of the feature: scene-by-scene, 24
    scenes is 24 independent budgets — up to 192 searches — and 24 slots of an
    hourly window that admits 5. One pool, set here, bounds the whole thing.

    30 against the 65 distinct claims the real draft produced. Not one search
    per claim, deliberately: the verifier answers from the room's own files
    first and only searches for what they do not cover, so the budget is for
    the gap rather than for the draft. If sweeps come back regularly reporting
    the budget exhausted, this is the number to move — and star/verdicts.py
    already distinguishes "we ran out of searches" from "we looked and it is
    not there", so the exhaustion is legible rather than silent.
    """
    return int(os.environ.get("STAR_MAX_SEARCHES_PER_SWEEP", "30"))


def sweep_extract_concurrency() -> int:
    """How many scenes a sweep reads at once.

    Extraction spends no searches, so this is not a cost ceiling — it is a
    bound on open sockets. Six keeps a 24-scene feature to four waves and a
    long one from opening eighty connections at a moment.
    """
    return int(os.environ.get("STAR_SWEEP_CONCURRENCY", "6"))


def sweep_timeout_seconds() -> int:
    """Wall-clock ceiling on each half of a sweep.

    Applied to the extraction fan-out and again to the single verification,
    rather than once around both: the two fail differently and a reader is
    owed which one stopped. Longer than a check's because a sweep is reading a
    whole draft, and still finite because this is a synchronous request a
    writer is watching.
    """
    return int(os.environ.get("STAR_SWEEP_TIMEOUT_SECONDS", "300"))


def max_annotation_chars() -> int:
    """Ceiling on a returned annotation file.

    An export of a 67-claim sweep with its excerpts runs well under 200KB, and
    this is the one endpoint that takes a file a writer edited elsewhere — so
    the bound is on what a sweep could plausibly have produced rather than on
    what a spreadsheet could plausibly save.
    """
    return int(os.environ.get("STAR_MAX_ANNOTATION_CHARS", "500000"))


def max_import_chars() -> int:
    """Ceiling on a research file being filed as rooms.

    Larger than the annotation ceiling because a chain export carries several
    rooms and every excerpt behind every finding: the two-room Doctor Who story
    exports at roughly 320KB. Doubled from there, so a story of five or six
    rooms lands and a library does not.
    """
    return int(os.environ.get("STAR_MAX_IMPORT_CHARS", "1500000"))


def max_rooms_per_import() -> int:
    """How many rooms one file may file at once.

    A story, not a library. The chain a check walks is capped at 12 rooms
    (star/chain.py's MAX_DEPTH) and importing a chain deeper than a check can
    read would file rooms the department could never use together.
    """
    return int(os.environ.get("STAR_MAX_ROOMS_PER_IMPORT", "12"))


def max_question_chars() -> int:
    """Ceiling on one requisitioned question.

    Far below the scene and treatment caps because this is a question, not a
    document. 300 characters is a long question and a short paragraph, and the
    ceiling is here to keep a treatment from being pasted into the field a
    researcher answers one question from — which would spend the budget of a
    requisition on work a build is shaped for.
    """
    return int(os.environ.get("STAR_MAX_QUESTION_CHARS", "300"))


def max_searches_per_question() -> int:
    """Per-requisition search budget, seeded into ADK session state.

    One question, one trip to the field. A build gets 30 for four categories
    from nothing and a check gets 8 for a whole scene; this answers a single
    question a writer asked because the room could not, and the researcher
    batches its queries into one `parallel_search` call anyway.

    Two, not one, and the second is for the case that makes this feature worth
    having rather than for headroom. A researcher that gets nothing usable back
    from its first call currently has no second move, and a requisition that
    files an empty answer costs the writer a slot of their hourly window and
    teaches them the department cannot help. One retry against a rephrased
    query is the difference between "not found" and "not looked for twice".
    """
    return int(os.environ.get("STAR_MAX_SEARCHES_PER_QUESTION", "2"))


def check_timeout_seconds() -> int:
    """Wall-clock ceiling on one script check.

    Well under Cloud Run's 900s request timeout, because a check is answered
    in the request that asked for it rather than through the run registry. A
    build gets 600s and salvages what the researchers already filed; there is
    nothing partial worth salvaging from a scene check, so this ceiling turns
    into a failure that names the cap rather than into a partial result.
    """
    return int(os.environ.get("STAR_CHECK_TIMEOUT_SECONDS", "180"))


# EVERY origin this service answers on, and there are four. That is not
# defensive breadth, it is the count.
#
# This paragraph replaced one that opened "The two origins this service is
# actually served from" and sat, for a while, directly above a four-entry tuple.
# Worth leaving the scar visible: that is the same defect class this project
# keeps catching in its own copy, a comment asserting a count the code beside it
# disproves, and it survived a commit because the edit that made it wrong added
# a paragraph instead of replacing one.
#
# `star.626labs.dev` is the canonical one: a Cloud Run domain mapping, serving
# the same revision under a valid certificate. It is what a reader should see and
# what belongs on camera.
#
# The other two are Cloud Run's own, and both keep serving 200 whether or not
# anyone means them to. `gcloud run deploy` prints the project-number form AND a
# hash form, and `services describe --format='value(status.url)'` reports the
# HASH form as canonical, which is a third answer again.
#
# Why the list rather than one entry: web/auth.js sends `location.origin + "/"`
# as its OAuth redirect_uri, so the origin a reader happens to arrive on is the
# one Google is asked to match. Registering a subset is what made the
# account-linking button fail with redirect_uri_mismatch on the live site while
# the identical flow passed from a script pointed at a different hostname. The
# OAuth client's Authorized redirect URIs need this same set, with trailing
# slashes, and that is a console step no code here can perform.
_DEFAULT_MCP_ORIGINS = (
    "https://star.626labs.dev",
    "https://star-390753828501.us-central1.run.app",
    "https://star-cdhog5ebsq-uc.a.run.app",
    "http://localhost:8000",
)


def mcp_allowed_origins() -> tuple[str, ...]:
    """Origins the MCP door answers to when a browser names one.

    Only a browser sends `Origin`, and an absent header passes — see
    star/mcp/protocol.py's origin_allowed for why that is the point rather
    than a hole. This list exists for the case where a browser IS the client,
    which is where DNS rebinding lives.

    An empty or whitespace-only env var falls back to the defaults rather than
    to an empty list. An empty allow list would refuse every browser origin,
    which is a defensible posture but not one that should be reachable by
    setting a variable to the empty string by accident.
    """
    raw = os.environ.get("STAR_MCP_ALLOWED_ORIGINS", "")
    origins = tuple(one.strip() for one in raw.split(",") if one.strip())
    return origins or _DEFAULT_MCP_ORIGINS


def room_retention_days() -> int:
    """How long a deleted room stays recoverable before it is destroyed.

    Thirty days: long enough that a delete regretted the next morning, or the
    next week, is still a mistake and not a loss; short enough that "deleted"
    means something and a workspace actually empties. The window is disclosed to
    the reader at the moment they delete and on the consent screen, so changing
    it here changes what the app promises — it is not a tuning knob.
    """
    return int(os.environ.get("STAR_ROOM_RETENTION_DAYS", "30"))


def max_rooms_per_ip_per_hour() -> int:
    """Per-caller ceiling on a public endpoint that spends money to answer."""
    return int(os.environ.get("STAR_MAX_ROOMS_PER_IP_PER_HOUR", "5"))


def max_rooms_per_day() -> int:
    """Global kill switch. One build is roughly 15 searches; 100 builds a day
    is a generous demo allowance and a cheap disaster ceiling."""
    return int(os.environ.get("STAR_MAX_ROOMS_PER_DAY", "100"))


def max_rate_limiter_keys() -> int:
    """Bound on distinct callers `_ip_limiter` tracks at once (Finding 3b).

    Reordering the daily cap behind the per-IP check (Finding 3) removed an
    accidental bound: the daily cap used to turn away identity-rotating
    callers before they ever reached the per-IP limiter's dict, capping it
    near the daily cap's own size. With the per-IP check running first, that
    accident is gone, so RateLimiter needs an explicit bound of its own. A
    few thousand distinct callers a day is generous for a hackathon demo and
    still cheap for the O(n) stale-key sweep in RateLimiter.check() to walk
    on every request, on a single-threaded loop shared with every open SSE
    stream.
    """
    return int(os.environ.get("STAR_MAX_RATE_LIMITER_KEYS", "5000"))


def max_synthesis_output_tokens() -> int:
    """Hard ceiling on the bible, because generation runs away without one.

    Measured 2026-08-09: gemini-3.6-flash generates at roughly 115 tokens/sec
    and permits 65,536 output tokens, so an unbounded synthesis call can spend
    9.5 minutes before it stops on its own. One did. Good bibles have run
    11,000-17,000 characters, comfortably under 6,000 tokens; 16,000 leaves
    generous headroom while capping the worst case near two minutes.
    """
    return int(os.environ.get("STAR_MAX_SYNTHESIS_TOKENS", "16000"))


def synthesis_thinking_level() -> str:
    """How hard the editor is allowed to think before it starts writing.

    `max_output_tokens` on a thinking model bounds thinking PLUS output, and
    thinking runs first, so the two compete and thinking wins. A room with more
    research to weigh deliberates longer, leaves less budget for the writing,
    and the response stops mid-word with a normal finish and nothing raised.

    The diagnosis was right and the CONTROL WAS WRONG. `thinking_budget` is the
    Gemini 2.5 knob; `gemini-3.6-flash` takes `thinking_level` and ignores a
    budget entirely. So the "fix" that shipped on 2026-08-10 set a 4,000-token
    allowance that was never applied, and the bibles kept arriving in pieces
    for another day and a half while the config said the problem was solved.

    Replayed 2026-08-11 against the Lenin Shipyard room's own findings — one
    model call per row, same prompt, same 16,000 ceiling:

        thinking_budget=4000   MAX_TOKENS   15,358 thinking    638 out   1 of 4
        thinking_level=MEDIUM  MAX_TOKENS   15,356 thinking    640 out   0 of 4
        thinking_level=LOW     STOP          7,400 thinking  4,096 out   4 of 4
        thinking_level=MINIMAL STOP              0 thinking  4,544 out   4 of 4

    The budget row and the MEDIUM row are the same run to within two tokens,
    which is what "silently ignored" looks like from the outside.

    LOW over MINIMAL, deliberately. Both finish, and MINIMAL is marginally
    longer, but this call is the one place in the pipeline where four
    researchers' findings get weighed against each other and ordered for a
    writer. Buying that judgement for 7,400 tokens inside a ceiling that has
    room for it is the trade this step exists to make; MINIMAL is the setting
    to reach for if a future model makes deliberation cheap enough not to
    matter, or expensive enough not to afford.
    """
    level = os.environ.get("STAR_SYNTHESIS_THINKING_LEVEL", "LOW")
    # Checked against the SDK's own enum, and raised rather than warned.
    #
    # This is the whole lesson of the defect, generalised. The genai client
    # accepts an unrecognised level with a UserWarning and carries on with the
    # model's default — which is precisely how a setting can be present, wrong,
    # and invisible for a day and a half. A misconfigured ceiling on the one
    # call that writes the product is not a thing to warn about, and the app
    # reads this once at import, so failing here fails at boot with the name of
    # the bad value in it.
    valid = {member.name for member in ThinkingLevel}
    if level not in valid:
        raise ValueError(
            f"STAR_SYNTHESIS_THINKING_LEVEL={level!r} is not a thinking level "
            f"this SDK knows. Valid: {', '.join(sorted(valid))}."
        )
    return level


def max_sources_per_category() -> int:
    """Cap the source list handed to synthesis.

    Deliberately generous. This started at 25 on the theory that a long source
    list was inflating synthesis output, but measurement did not support it:
    bibles came in at 6.2k, 16.5k, and 16.5k characters across runs whose
    caps differed, and the spread within a single cap was as wide as the
    spread between caps. Run-to-run variance swamps this knob.

    The real runaway guard is max_synthesis_output_tokens, which bounds the
    output directly rather than guessing at an input that correlates with it.
    This cap stays only to keep a pathological source list from bloating the
    prompt, and 60 is well above what any observed run produced per category.
    """
    return int(os.environ.get("STAR_MAX_SOURCES_PER_CATEGORY", "60"))


def max_runs_in_memory() -> int:
    """Cap on live entries in `star.server._runs`.

    Each entry holds a `SourceLedger` carrying every excerpt from up to
    `max_searches_per_build()` searches, plus a task reference — nothing
    ever shrinks it on its own. Persistence (star/store.py) is what makes
    eviction safe: a run dropped from memory once it reaches a terminal
    status is still readable back from Firestore via get_room's fallback.
    """
    return int(os.environ.get("STAR_MAX_RUNS_IN_MEMORY", "20"))


def run_timeout_seconds() -> int:
    """Wall-clock ceiling on one room build.

    Independent of any model-level cap: a hung network call, a retry storm, or
    a future agent with its own limits should still surface as a visible error
    rather than a UI that spins forever and a container that never frees the
    connection.

    Raised from 420 to 600 after a legitimate, non-pathological run tripped the
    420s ceiling. Observed durations for one fixed treatment ranged from 146s
    to over 420s, so a ceiling that normal runs hit is a ceiling that turns
    slowness into failure. This is a backstop, not a performance budget: the
    pipeline's duration variance is a separate problem and a real demo risk.
    """
    return int(os.environ.get("STAR_RUN_TIMEOUT_SECONDS", "600"))


# --- The authorization server (docs/spec-oauth-as.md) -----------------------

# The canonical URI this deployment is a protected resource under, and the one
# string an OAuth access token's audience is compared against on every MCP
# call. It is the first entry of _DEFAULT_MCP_ORIGINS repeated rather than read
# from it, and the repetition is deliberate: that tuple is env-overridable and
# order-sensitive, so deriving the audience from `mcp_allowed_origins()[0]`
# would let a change to the Origin allow list quietly move what a token is
# valid FOR. Two facts that happen to share a hostname today, kept apart.
#
# No path. RFC 9728 derives the metadata URL from the resource identifier, and
# a resource of `https://star.626labs.dev` puts that document at
# `/.well-known/oauth-protected-resource` — which is the path
# `spec-oauth-as.md > Endpoints` names. A resource of
# `.../mcp` would move the document to
# `/.well-known/oauth-protected-resource/mcp` and contradict the spec's own
# table. See star/oauth/metadata.py for the ambiguity that leaves.
_DEFAULT_CANONICAL_RESOURCE = "https://star.626labs.dev"


def canonical_resource() -> str:
    """The resource identifier tokens are bound to and validated against."""
    return os.environ.get("STAR_CANONICAL_RESOURCE", _DEFAULT_CANONICAL_RESOURCE)


def oauth_access_token_seconds() -> int:
    """How long an OAuth access token is good for.

    One hour, and `spec-oauth-as.md > Open questions` #3 is explicit that this
    is an assumption rather than a measurement: nothing has yet recorded how
    often a long-running agent session trips a refresh. It is short because the
    spec's requirement is short-lived access tokens with refresh rotation, and
    an env var is here so the number can be moved once something measures it.
    """
    return int(os.environ.get("STAR_OAUTH_ACCESS_TOKEN_SECONDS", "3600"))


def oauth_refresh_token_seconds() -> int:
    """How long a refresh token is good for, absent rotation.

    Thirty days. Rotation means a working client renews this every hour, so
    the ceiling only decides how long a client can be OFF before its operator
    has to approve the connection again. It is a bound rather than a feature:
    a refresh token that never expires is a permanent credential issued
    without anyone deciding it should be one.
    """
    return int(os.environ.get("STAR_OAUTH_REFRESH_TOKEN_SECONDS", "2592000"))


def max_authorization_codes() -> int:
    """Bound on live authorization codes held in memory at once.

    The same bound `max_rate_limiter_keys` puts on RateLimiter and for the
    reason star/guards.py:31-54 documents: the stale sweep is O(n) and runs on
    the single-threaded loop every open SSE stream shares, so the number of
    tracked keys is a cost every caller pays. Codes live 60 seconds, so this
    is a ceiling on concurrent in-flight consents, not on daily volume.
    """
    return int(os.environ.get("STAR_MAX_AUTHORIZATION_CODES", "5000"))


def validate_env() -> None:
    """Fail fast on missing keys (review fix M5) instead of mid-pipeline.

    Phase 2 made three more variables load-bearing, and all three fail
    *closed but silently* when absent: `star/auth.py` and `star/store.py`
    read the project id, and `/config.js` serves the API key to the browser.
    With no project id, `firebase_admin` raises inside `_verify`,
    `verify_token` swallows it, and every `/api/` call just 401s — a missing
    env var and a network blip look identical to the user. Checking here
    makes that class of misconfiguration loud at boot instead.
    """
    missing = []
    if not os.environ.get("PARALLEL_API_KEY"):
        missing.append("PARALLEL_API_KEY")
    using_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() in ("TRUE", "1")
    if not using_vertex and not os.environ.get("GOOGLE_API_KEY"):
        missing.append("GOOGLE_API_KEY")
    # Vertex authenticates with the runtime's own identity and reads WHERE to
    # send the call off the environment instead. Both of these fail the way
    # this function exists to prevent — silently and late. With no location
    # google-genai falls back to a region the pinned model is not published in
    # (gemini-3.6-flash is `global`-only on Vertex, 404 in us-central1), and
    # the first model call 404s minutes after intake told the writer yes.
    if using_vertex:
        if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
            missing.append("GOOGLE_CLOUD_PROJECT (needed with GOOGLE_GENAI_USE_VERTEXAI)")
        if not os.environ.get("GOOGLE_CLOUD_LOCATION"):
            missing.append("GOOGLE_CLOUD_LOCATION (needed with GOOGLE_GENAI_USE_VERTEXAI)")
    # Either satisfies star/auth.py's _get_app and star/store.py's client
    # property, which both accept the same fallback — see those modules.
    if not (os.environ.get("FIREBASE_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")):
        missing.append("FIREBASE_PROJECT_ID (or GOOGLE_CLOUD_PROJECT)")
    if not os.environ.get("FIREBASE_API_KEY"):
        missing.append("FIREBASE_API_KEY")
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill them in."
        )
