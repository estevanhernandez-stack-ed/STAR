# The department, after the glow campaign

**Date:** 2026-08-11
**Register:** [`superpowers/research/2026-08-10-star-ui-audit-findings.md`](superpowers/research/2026-08-10-star-ui-audit-findings.md) — 25 rows, 25 clean
**Measuring stick:** [`superpowers/specs/2026-08-10-star-design-language.md`](superpowers/specs/2026-08-10-star-design-language.md)
**Evidence:** round 1 in [`ui-evidence/`](ui-evidence/), round 2 in [`ui-evidence/round-2/`](ui-evidence/round-2/)

Seven waves, 25 findings, 623 tests. What follows is what a writer will actually
notice, and the numbers behind each one.

## The card that answers a paid question

This is the change that matters most, because it is the surface the product
exists for: you check a scene, and the department shows its work.

Before, that card ran **1730px** in an 830px window — every one of the nine cards
in a filed check needed scrolling — and **82% of it was raw scraped markdown**.
Wikipedia table rows, `[[ 12 ]]()` citation markers, `#` heading marks, bare
image links, rendered as literal characters. The one line you came for was
**1.2%** of the card.

Now the card is **764px**, fits on screen, and the quotation reads as prose. The
excerpt went from a median of **1462 characters to 244**, and **0 of 104**
excerpts across the two stored rooms carry markup where every one of them did.

The order changed with it. The verdict's scope became a slug beside the stamp
instead of a paragraph above the answer, and the standing caveat moved below the
evidence it describes. The source quotation now ranks where the answer belongs:
a median **62.2%** of the card.

## The department tells you when it fails

A failed build used to leave "The department is working" on screen with the
ellipsis still pulsing. It now says it stopped, above the drawers rather than
buried under four full-height cards, with a way to start again that keeps your
treatment.

A run that errored or was interrupted is legible in the rail — the marker was
**2.79:1** against its ground and **2.37:1** on the selected row, both under the
3:1 floor, and carried the fact in colour alone. It is now **3.87:1** and
**3.28:1**, and the row says **Stopped** or **Interrupted** in words, which are
two different events and no longer one.

## Your work stops disappearing

- A run in flight now has its own rail row and a way back to it. Walking away
  warns you first, and says plainly that the build keeps going and keeps
  spending.
- Reload, lock your phone, or crash mid-build and the run resumes.
- Coming back to the room you are already in no longer wipes a scene you have
  not submitted.
- A token issued during a build survives the build finishing.

## It works without sight or a mouse

The whole of wave 3, and none of it is visible in a screenshot. A 146-to-420
second build announced nothing at all; it now has one. Every failure message in
the app was silent; they now carry `role="alert"`. The answer to a check arrived
with no scroll and no focus move; focus now goes to it. The scene you pasted
could not be reached by keyboard in Safari; it is a named region with a tab stop.

Whether a screen reader speaks all of this at the right moment is a manual check
this campaign could not make, and every close-out says so.

## The details you feel without naming

The drawer you click comes with you instead of leaping 623px below the fold. The
hanging folder's cut tab tucks behind the card face — it had **1.6px** of overlap
where the construction needs about 9. The bible stopped spending the type ramp's
top step twice in 50px, and its card stopped sitting 8px inboard of the one above
it. The tally says **17 web searches** rather than **17 cited web searches**,
because the count is taken before any search comes back and "cited" claimed two
things it could not know.

## What did not change, on purpose

The identity. THE MORGUE was already built; this campaign measured against it
rather than replacing it. The proof is that the room's composition is the same
after seven waves as before them: manila holds **70.71%** of the filed room's
stage against a 40% floor, where round 1 measured **70.70%**, with onionskin at
**1.21%** in both. Same capture, same method, both rounds.

## Shipping

This repo's release is `scripts/deploy.sh` to Cloud Run. It has no tags, no
CHANGELOG and no version ritual, so none was invented here. The deploy needs
`GOOGLE_OAUTH_CLIENT_ID` and gcloud credentials and is the builder's to run.
