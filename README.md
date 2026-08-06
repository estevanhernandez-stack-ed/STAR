# STAR — Story & Treatment Agentic Research

**Every studio has a research department. Now every writer does.**

STAR is a multi-agent research department for screenwriters, built with
**Google ADK (`google-adk`)** and **Gemini** on Google Cloud, using
**Parallel's Search API** (via the official **`parallel-web`** SDK) for live,
cited web research at runtime.

Give STAR a treatment or logline and it builds your research bible — setting
& atmosphere, objects & props, logistics, forces & conflicts — with every
fact cited to a live web source. Then upload a scene, and STAR keeps your
script honest: every real-world claim is verified and flagged as confirmed,
anachronism, or unverifiable, with receipts.

Built for the **Agentic Cinema: The Blockbuster Hackathon** (Parallel track).

## Architecture

Deterministic multi-step pipelines built as ADK workflow agents — not a
free-roaming chat loop:

```
Pipeline A · Build the Room  (SequentialAgent)
  IntakeAgent      treatment → StoryProfile               [Gemini]
  PlannerAgent     StoryProfile → ResearchPlan            [Gemini]
  ResearchFanout   ParallelAgent: 4 category researchers,
                   each calling Parallel Search API       [Gemini + parallel-web]
  SynthesisAgent   excerpts → cited research bible        [Gemini]

Pipeline B · Script Check  (SequentialAgent — coming in week 3)
  ClaimExtractor → Verifier (room lookup + turbo search) → Annotator
```

## Quickstart

```bash
# 1. Environment (Python 3.11+)
python -m venv .venv
.venv\Scripts\activate          # Windows   (source .venv/bin/activate on mac/linux)
pip install -e .

# 2. Keys
copy .env.example .env          # then fill in:
#   GOOGLE_API_KEY   — Google AI Studio (Gemini)
#   PARALLEL_API_KEY — platform.parallel.ai

# 3. Smoke-test the Parallel Search integration
python scripts/try_search.py

# 4. Run the agent in the ADK dev UI
adk web                          # open the URL it prints, pick "research_dept"
```

In the ADK web UI, paste a short treatment (era, place, genre, premise) and
watch the pipeline run — the trace inspector shows each agent step and every
Parallel Search call with its arguments and results.

## Runtime services (hackathon compliance)

- `google-adk` / `google-genai` — imported and called: `star/agents/*.py`
- `parallel-web` (Parallel **Search API**) — imported and called at runtime:
  `star/tools/parallel_search.py`
- All AI at runtime is Gemini on Google Cloud. No other AI models or APIs.

## License

MIT — see [LICENSE](LICENSE).
