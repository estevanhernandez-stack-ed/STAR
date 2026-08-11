# Capture checklist — vibe-glow baseline

Every round re-shoots this list at 1440x900 against local `uvicorn`, one
`default` theme round (STAR has no theming system: one `:root` in
`web/tokens.css`, no `prefers-color-scheme`, no switcher). Files land in
`docs/ui-evidence/` as `NN-<surface>--default.png`, gitignored.

Reach-paths are recorded so re-capture after a wave is mechanical rather than
re-derived. Where a surface needs data, the room built for the baseline round
is reused; a wave that changes markup does not need a fresh pipeline run.

| NN | Surface | Reach-path | Needs |
| --- | --- | --- | --- |
| 01 | `intake-empty` | `GET /`, first visit, no rooms filed. Also serves as the empty-rail shot | — |
| 02 | `intake-pasted` | paste the baseline treatment into the treatment field, do not submit | — |
| 03 | `consent` | `GET /consent.html` | — |
| 04 | `account` | open the account panel from the rail | — |
| 06 | `progress-running` | submit the treatment, shoot while the four researchers are mid-search | build |
| 06b | `progress-filed` | all four have stamped `Filed`, synthesis still running | build |
| 07 | `room-filed` | the run completes and the results panel lands on the drawer grid | build |
| 08 | `drawer-expanded` | `button[aria-label="Open the drawer: Objects & Props"]`, stage at top | build |
| 08b | `drawer-clips` | same drawer, stage scrolled to the clip stack | build |
| 09 | `drawer-flagged` | element shot of the finding card carrying an `UNSOURCED` clip | build |
| 10 | `bible` | open the research bible from the filed room | build |
| 11 | `rail-filed` | `GET /` with the baseline room saved | build |
| 12 | `check-empty` | open Script Check on the filed room, scene field empty | build |
| 13 | `check-annotated` | paste the baseline scene, run the check, scene comes back marked | check |
| 14 | `check-citation` | click one mark, citation rail open on its verdict | check |

There is no `05`. The empty rail is the same page state as `01` and shooting it
twice would be two names for one piece of evidence.

## The capture rule this app needs

`fullPage: true` is a **no-op here and must not be trusted.** The document never
scrolls: `#stage` is the scroll container, and on a filed room it holds 1680px
of content in an 832px box (4870px with a drawer expanded). A `fullPage` shot
returns the viewport at whatever position `#stage` happened to be left in, which
is how the first round produced five mid-scroll captures that looked deliberate.

So every capture sets the scroll position explicitly first:

```js
document.querySelector('#stage').scrollTop = 0;   // or an explicit offset
```

and shoots the **viewport**, not the page. Two consequences worth stating:

- The canonical shot is the composition at the fold, which is what the design
  language governs and what a reader actually meets.
- A surface whose tail matters gets a second numbered shot at an explicit
  offset (`08b`) rather than a layout mutation to force the whole thing into one
  frame. Editing `overflow` or `height` to capture a page changes the thing
  being measured, and evidence that had to be reshaped is not evidence.

## What the round is measured against

`docs/design/DIRECTION.md` and the design-language doc it is promoted into.
The nine invariants in `.vibe-glow/state.json` outrank any finding this
evidence produces.

## Notes for the shooter

- Screenshot after idle. The stamp press is a 220ms animation and a capture
  mid-press is motion evidence, not layout evidence.
- 07 is the surface the manila-area invariant governs. Shoot it full-page, in
  the filed state, with the drawers closed.
- Auth is silent and anonymous, so a fresh browser profile starts with an empty
  rail. 01 and 05 are the same page state and are shot once each only because a
  later round may diverge them.
