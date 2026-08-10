"""Three postures pointed at the same four tools.

They differ in the two things that actually change what an agent experiences on
this door: **what it already has** (a filed room, or an account with nothing in
it) and **how well it is wired** (tool schemas taken from `tools/list`, or
argument names guessed from a stale note). A third persona that merely asked
different questions would be one persona run three times.

  1. `writer`     — knows what it wants, correctly wired, has a room to work
                    against. The happy path, plus the one question
                    `spec.md > Open issues` #6 asks: a scene from a different
                    story entirely.
  2. `fumbler`    — correctly *connected* and badly *wired*. It reaches the
                    door through a generic passthrough call and writes its own
                    argument JSON from a note that names the tools and not
                    their arguments. This is the real shape of the failure the
                    error strings exist for, and it is not reachable by handing
                    a model the real schemas — a model given a correct
                    `FunctionDeclaration` cannot easily send `roomId`, so
                    testing that refusal means taking the schema away.
  3. `newcomer`   — a fresh account with no rooms, correctly wired, and
                    holding one room id it did not get from `list_rooms`. Two
                    empty states in one run: an account with nothing filed, and
                    an id that belongs to somebody else.

Two scenes are written here rather than left to the model. The content of a
scene decides what the check spends and what it can possibly conclude, so
letting a model improvise one would make the result a fact about the model
instead of a fact about the department.

`Budget` is the spend guard, and it is a harness concern rather than a server
one. `check_scene` costs real money against the same daily cap the live demo
draws on (`spec.md > Open issues` #7), so a persona that decides to loop must
be stopped by the runner, not by the department's wallet. A blocked call is
recorded in the transcript as a harness block and never as a service response —
the audit is about what the *service* said, and a sentence the harness wrote is
not evidence about that.
"""

from dataclasses import dataclass, field

# The room every spending persona works against: a 1962 Memphis story, filed
# `complete`, 15 searches. Built before this item and reused rather than
# rebuilt, which is `spec.md > Open issues` #7's own mitigation — the personas
# run against an already-built room so only `check_scene` spends.
ROOM_ID = "92f7835ac882"


# A scene from the same story as the room. Written to sit across the seam the
# check is supposed to expose: WDIA, the Satellite record shop, acetates,
# lacquer and union scale are all things the room's own drawers carry, and the
# Moog is not — it is the planted anachronism, and 1962 is two years early for
# one. So a correct check answers most of this from the room and spends a
# search on the part the room cannot answer.
SCENE_ON_STORY = """INT. SATELLITE RECORD SHOP, MCLEMORE AVENUE - DAY

DELIA, 24, leans on the counter thumbing the acetate she cut last night.
Outside, a bus grinds up McLemore.

DELIA
It runs three-forty. They'll never spin it.

RAY drops a nickel in the till and slides a Moog synthesizer catalogue
across the glass.

RAY
WDIA has a new man on the afternoon shift. He'll spin anything that moves.

Delia turns the acetate to the light. The lacquer has already gone grey at
the edges.

DELIA
Union scale is forty-one fifty a session. I did four last week and I still
cannot make the rent.
"""

# A scene with nothing whatsoever to do with the room, which is the whole of
# `spec.md > Open issues` #6. Different decade, different country, different
# subject. Everything checkable in it - the phone, the quota system, the bay,
# the sea state - is outside a 1962 Memphis music room by construction, so the
# room's files can answer none of it. The accented names are deliberate too:
# they take a non-ASCII round trip through extraction, search and the JSON on
# the wire, and one live pass over that is worth having.
SCENE_OFF_STORY = """INT. TRAWLER HAFDIS - GALLEY - NIGHT

SIGRUN, 40s, braces against the roll and pours coffee from a dented thermos.
A Nokia 5110 buzzes on the table, its screen green in the dark.

SIGRUN
The quota is sold. Thorlakshofn to a company in Akureyri, and nobody on this
boat was asked.

BJARNI wipes diesel from his hands.

BJARNI
Then we fish for them. Same nets, somebody else's ledger.

Above them the radio crackles: gale warning, force nine, Faxafloi.
"""


@dataclass(frozen=True)
class Budget:
    """How many spending calls one persona is allowed the department to accept.

    Counted on ACCEPTED calls rather than on attempts, and the difference is
    not pedantry. A call refused on its arguments, or on a room this account
    does not own, never reaches a pipeline and buys no searches — charging a
    persona for it means the one call it was going to get right is the one it
    is denied. Searches themselves are the wrong unit in the other direction:
    the harness cannot know what a call will spend until it comes back.
    """

    build_room: int = 0
    check_scene: int = 0

    def allowance(self, tool: str) -> int | None:
        """The ceiling for one tool, or None when the tool spends nothing."""
        return {"build_room": self.build_room, "check_scene": self.check_scene}.get(tool)


@dataclass(frozen=True)
class Persona:
    """One posture, and everything the runner needs to drive it."""

    slug: str
    name: str
    posture: str
    # "declared" hands the model the real inputSchema from `tools/list`.
    # "passthrough" hands it one generic call and makes it write its own
    # argument JSON, which is the only way to test a wrong argument name.
    wiring: str
    account: str  # "primary" (has the room) | "empty" (a fresh uid, no rooms)
    system: str
    opening: str
    max_turns: int
    budget: Budget = field(default_factory=Budget)


WRITER = Persona(
    slug="writer",
    name="A writer who knows what they want",
    posture=(
        "Correctly wired, holding an account with one filed room, and arriving "
        "with two scenes and a specific question about each."
    ),
    wiring="declared",
    account="primary",
    max_turns=8,
    budget=Budget(build_room=0, check_scene=2),
    system=(
        "You are a research assistant working for a screenwriter. You have "
        "access to their research department over MCP. Work through the "
        "writer's request end to end using the tools, one step at a time, and "
        "do not ask the writer questions you could answer by calling a tool. "
        "Do not start a new research build under any circumstances; the writer "
        "has the room they need already. When you are finished, write the "
        "writer a short plain-language report of what you found, naming any "
        "claim that came back as an anachronism and what the source behind it "
        "was."
    ),
    opening=(
        "I have a room filed for my 1962 Memphis script and I want two scenes "
        "checked against it.\n\n"
        "Find the room first, look at what is actually in it, then check this "
        "scene from the script:\n\n"
        "<scene-one>\n"
        f"{SCENE_ON_STORY}"
        "</scene-one>\n\n"
        "Then check this second scene. It is from a completely different "
        "project of mine, set on an Icelandic trawler, and I want to know "
        "whether checking it against the Memphis room tells me anything useful "
        "or whether I am wasting my time:\n\n"
        "<scene-two>\n"
        f"{SCENE_OFF_STORY}"
        "</scene-two>\n\n"
        "Tell me what each scene got back, and for scene two tell me straight "
        "whether that answer was worth having."
    ),
)


FUMBLER = Persona(
    slug="fumbler",
    name="An agent that gets the arguments wrong",
    posture=(
        "Connected correctly and wired from a stale note that lists the tool "
        "names and none of their arguments, so every argument it sends is a "
        "guess it has to correct from what comes back."
    ),
    wiring="passthrough",
    account="primary",
    max_turns=12,
    budget=Budget(build_room=0, check_scene=1),
    system=(
        "You are an autonomous agent with one generic way to reach a remote "
        "tool server: `star_call`, which takes the name of a tool and a JSON "
        "string of arguments that YOU write. Nothing validates that JSON "
        "before it is sent, so the argument names and types are entirely your "
        "responsibility.\n\n"
        "Your integration notes are old and list only tool names. Send your "
        "best guess, read what comes back, and correct yourself from it. Never "
        "repeat a call that has already been refused in exactly the same way. "
        "Never call a tool that starts a new research build. When you cannot "
        "get any further, stop and write down, for each failure you hit, "
        "whether the response alone told you what was wrong and how to fix it."
    ),
    opening=(
        "Task: check a scene against the research room whose id is "
        f"{ROOM_ID}, and report the verdicts.\n\n"
        "Integration notes (last updated some time ago, arguments not "
        "recorded):\n"
        "  tools available: list_rooms, get_room, build_room, check_scene, "
        "get_status\n\n"
        "The scene:\n\n"
        f"{SCENE_ON_STORY}"
    ),
)


NEWCOMER = Persona(
    slug="newcomer",
    name="An agent starting from an empty account",
    posture=(
        "Correctly wired, holding a token for a real account that has never "
        "filed anything, plus one room id somebody else mentioned."
    ),
    wiring="declared",
    account="empty",
    max_turns=8,
    # One `check_scene` is allowed on purpose. This account owns no room, so
    # any check it attempts is refused before a search is bought - and a
    # cross-account read refused for free is exactly the property worth
    # watching a persona discover.
    budget=Budget(build_room=0, check_scene=1),
    system=(
        "You are an autonomous agent that has just been given credentials for "
        "a remote research service you have never used. Find out what you can "
        "actually do with this connection before you commit to anything, and "
        "prefer calls that cost nothing. Do not start a research build: you "
        "are not authorised to spend money on this account. When you have "
        "established what this connection can and cannot do, stop and report "
        "it plainly, including anything you could not explain from the "
        "responses you got."
    ),
    opening=(
        "You have just been handed a token for a service called STAR. Nobody "
        "told you what is in the account.\n\n"
        "A colleague said they had 'a Memphis room' on the same service and "
        f"gave you its id, {ROOM_ID}, and said to take a look at it.\n\n"
        "Work out what this connection gives you, whether that room is "
        "reachable, and report back."
    ),
)


PERSONAS = (WRITER, FUMBLER, NEWCOMER)
BY_SLUG = {persona.slug: persona for persona in PERSONAS}
