"""One question, sent back to the field, filed into a room that already exists.

A room is a snapshot of the treatment it was built from, and it starts going
stale the moment a writer keeps working. `ask_room` reads what is already
filed and spends nothing; when it comes up dry, the only move the department
offered was `build_room` — a fresh room, several minutes, a dozen searches and
a slot of the daily budget, to answer one question. So a writer with a
question the room did not cover either paid for a whole second room or went
somewhere else, and the room stayed exactly as stale as it was.

This is the missing middle. One question, one researcher, one trip to the
field, and the answer is filed into the room the writer already has rather
than into a new one beside it. The room grows with the project instead of
freezing at intake.

NO NEW AGENT. `make_researcher` is the same researcher a build fans out four
of, and it is used here unchanged: same brief, same output format, same
injection guard, same `parallel_search` tool. The only difference is the plan
it is handed — one question instead of the planner's eight to twenty — which
is why a requisitioned finding parses through `star/findings.py` exactly like
a built one and is hydrated out of a ledger exactly like one. A second
researcher written for this path would be a second set of those rules,
drifting from the first, and the first is the one the product's claims are
about.
"""

from google.adk.runners import InMemoryRunner

from star import config
from star.agents.researchers import make_researcher
from star.models import Category

APP = "star-question"
USER = "requisition"

# One runner per category, built once at import, mirroring the module-level
# `_runner` and `_check_runner` in star/server.py. A researcher is bound to
# its category at construction — the brief, the output key and the "answer
# ONLY this category" instruction are all baked in — so there is no single
# agent that could serve every requisition, and building one per call would
# pay that construction on every question a writer asks.
RUNNERS: dict[Category, InMemoryRunner] = {
    category: InMemoryRunner(agent=make_researcher(category), app_name=APP)
    for category in Category
}

# The turn that starts the run. The question itself is NOT here: it travels in
# state, inside the `<research_plan>` markers, for the same reason
# star/agents/script_check.py keeps a scene out of the user turn. A question
# posted as the user message would arrive in instruction position, which is
# the one place the delimiters exist to keep writer-supplied text out of.
TURN = "Research the question in the plan and report your findings."


def question_state(question: str, category: Category) -> dict:
    """The session state one requisition runs on.

    `research_plan` is shaped like the planner's own output rather than as a
    bare string, because the researcher's prompt reads it as a plan and filters
    it by category. A shape it half-recognises is how a researcher comes back
    having answered nothing and said why in prose no parser reads.

    `why` is honest about its own provenance. The planner fills it with the
    scene-writing need a question serves, which it knows because it wrote the
    question from the treatment; here the writer asked directly and nothing in
    this process knows more than that.

    `search_budget` is read by star/tools/parallel_search.py. Seeding it is
    what stops one question from spending a build's thirty searches.
    """
    return {
        "research_plan": {
            "questions": [
                {
                    "category": category.value,
                    "question": question,
                    "why": "Asked directly by the writer about a filed room.",
                }
            ]
        },
        "search_budget": config.max_searches_per_question(),
    }
