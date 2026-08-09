# STAR — three visual directions

**Date:** 2026-08-09
**For:** the four-quadrant room, the receipts, and an audience that has been burned by AI products
**Status:** proposal, pick one

---

## First, the thing nobody wants to say about what exists

The current surface is `--bg: #0f1115`, `--accent: #e3b341`, `font-family: Georgia`. That is trap 2 with a serif laid over it.

- **`#0f1115` is near-black.** Not "dark editorial" — near-black. It is the default ground of every generated dark UI shipped in the last two years.
- **`#e3b341` is one accent doing every job.** It marks the brand, the buttons, the links, the active tab, the in-progress state, the warning state, and the blockquote rule. When one hue means seven things it means nothing, and the specific hue is the single most common accent in AI-generated "premium dark."
- **Georgia is not a choice, it is the absence of one.** It ships on the machine. It has no small caps, no optical sizes, no old-style figures, and lining numerals that fight every count in the UI. A working screenwriter does not consciously identify Georgia, but they recognize a page that did not decide anything.

The `research department` voice in the copy is real design work and survives all three directions below. The palette and type do not.

One thing the existing spec got right that all three directions inherit: **color acquires a job.** Working, filed, flagged, unverifiable. Four states, four distinguishable signals, never one gold doing all of it.

---

## The well I did not go back to

The obvious pulls are script format and Courier, the broadsheet, and the archive box. Script-format-as-a-whole-UI is Courier cosplay, it does not earn four quadrants (a script page is one column), and it is the first thing anyone reaches for. Broadsheet is explicitly trap 3. The archive box gives you a container and nothing else — no receipt mechanic.

What earns the structure is the **apparatus that existed specifically to prove where a fact came from**. Three of those existed in a 1962 studio's orbit, and each produces a different product:

1. The newspaper **clipping morgue** — the source stamp.
2. The **editing bench and contact sheet** — the edge code that ties a print to its negative.
3. The **card catalogue and archival finding aid** — the rod, and the bracket convention for information the archivist supplied rather than found.

All three are provenance machines. None of them are in the AI design cluster.

---

# Direction 1 — THE MORGUE

**Thesis:** STAR is the clipping library behind the newsroom, where nothing gets filed without a stamp saying who found it, where, and when.

Every large paper ran a morgue: a room of steel cabinets, subject-headed folders, and a clerk whose entire job was to cut, stamp, and file. The stamp carried publication, date, and the clerk's initials. **An unstamped clip was worthless** — not wrong, worthless, because you could not take it to an editor.

That is STAR's thesis stated as a physical object.

### Why it earns the structure

`ledger.py` already built a morgue. `LedgerEntry(url, title, excerpts, found_by: set[str])` is a clipping file: the clip, its publication, and which clerk pulled it. `Finding.unverified_urls` is the clip somebody dropped in the drawer without stamping. Four subject headings, four drawers. The mapping is not a metaphor stretched over the system; it is a description of it.

### Palette

| Hex | Name | Reasoning |
|---|---|---|
| `#232B27` | **Cabinet Green** | The olive-drab enamel of mid-century steel office furniture. Dark, but cold and green-shifted, so it reads as *furniture* rather than as "dark mode." This is the ground, and it is deliberately not `#0f1115`. |
| `#171D1A` | **Drawer Shadow** | The recessed well behind the folders. Insets, the treatment textarea, the sidebar. One step down, never to black. |
| `#D2B98C` | **Manila** | Actual folder stock. A saturated warm tan, three steps darker and considerably more chromatic than trap-1 cream. It is a *component* surface, not the page. |
| `#5C3D91` | **Aniline** | Rubber-stamp ink was aniline purple, which is why every surviving 1950s file card is stamped violet rather than black. Means **filed and verified**. Nobody's AI dark UI uses violet as its trust color. |
| `#B3341F` | **Oxide Red** | Second stamp pad. Means **flagged** — the anachronism verdict, and the `UNSOURCED` stamp on an unverified citation. Red because that is what the second pad was. |
| `#7E8B7F` | **Pencil** | Desaturated green-gray. Metadata, tab labels, secondary text, and the **unverifiable** state — a clip in the drawer that nobody ever got around to stamping. |

Color jobs: working = the empty stamp outline, pulsing. Filed = the stamp inked in Aniline. Flagged = Oxide Red. Unverifiable = Pencil, dim, unstamped. Note that *working* and *filed* separate by **form**, not hue — an outline becoming solid. That is stronger than two similar colors, and it survives colorblindness.

### Type

- **Display — Archivo Narrow** (Omnibus-Type, SIL OFL, self-hostable static or variable WOFF2). A condensed American gothic in the ATF form-and-label tradition. The morgue's entire visible typography is *labels*: drawer plates, folder tabs, stamp slugs. Archivo Narrow at Bold with wide tracking is a filing label. It is not a "display serif," which keeps the direction off trap 1 entirely.
- **Body — Newsreader** (Production Type, SIL OFL, self-hostable, variable with a real `opsz` axis). A news text face with genuine text color at 15–17px and an italic that carries block quotations without going decorative. The optical size axis is load-bearing: the bible is a long read at one size and the clipping excerpts are 12px captions at another, and one static face cannot serve both.
- **Utility — Sligoil** (Velvetyne Type Foundry, SIL OFL, self-hostable). A monospace drawn for subtitling and film-adjacent paperwork. Wide apertures that survive at 11px, which matters because it carries URLs, dates, counts, and stamp slugs. Fallback if the hinting disappoints in practice: **Sometype Mono** or **DM Mono**, both OFL.

**Why not the obvious pairing:** obvious here is Playfair or Lora or a Times revival over a Helvetica clone. Newsreader plus Archivo Narrow reads *press room* rather than *blog post*, and neither face appears in the generated-design vocabulary. All three are downloadable font files — no Google Fonts CDN link, which the zero-third-party-request rule forbids anyway.

**Explicitly forbidden in this direction:** multi-column body text and hairline gray rules. The morgue is the library *behind* the newspaper, not the newspaper. Cards and folders, not columns. That line is what keeps it off trap 3.

### Layout — the four-quadrant room

```
+----------------------------------------------------------------------------+
| * STAR   RESEARCH DEPARTMENT        1962 MEMPHIS            [ROOM] [CHECK]  |
|                                     1960-1962 . crime drama                 |
|                                     (Memphis) (Stax Studio) (McLemore Ave)  |
+-------------+--------------------------------------------------------------+
|  FILES      |    ______________         ______________                      |
| > Memphis   |   / SETTING      \_____  / OBJECTS      \_____                |
|   Noir 78   |  |                     ||                     |               |
|   Untitled  |  |  9 clips            ||  8 clips            |               |
|             |  |  17 stamped         ||  16 stamped         |               |
|             |  |                     ||                     |               |
| + NEW FILE  |  |        [ FILED ]    ||        [ FILED ]    |               |
|             |  |         12:04       ||         12:04       |               |
|             |  +---------------------++---------------------+               |
|             |    ______________         ______________                      |
|             |   / LOGISTICS    \_____  / FORCES       \_____                |
|             |  |                     ||                     |               |
|             |  |  6 clips            ||  5 clips            |               |
|             |  |  9 stamped          ||  11 stamped         |               |
|             |  |  .  .  .            ||  1 UNSOURCED        |               |
|             |  |      (searching)    ||                     |               |
|             |  |    [ ]  Memphis PD  ||     [ FLAGGED ]     |               |
|             |  |         vice, 1962  ||          12:05      |               |
|             |  +---------------------++---------------------+               |
+-------------+--------------------------------------------------------------+
```

Each quadrant is a hanging folder with a cut tab. Running: the tab pulses, the search objective shows in Sligoil under the count, and each landed search adds a dot. Filed: the stamp lands.

**Expanded** — the drawer pulls out onto the writing shelf every steel cabinet had:

```
+----------------------------------------------------------------------------+
| <- SETTING                          [ OBJECTS ][ LOGISTICS ][ FORCES ]     |
+----------------------------------------------------------------------------+
|  ASKED: What did the Stax recording room look like in 1962?                 |
|                                                                             |
|  Stax operated out of the old Capitol Theatre; the sloped theater floor     |
|  was never leveled and shaped the room's sound.                             |
|                                                                             |
|  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~   <- cut edge            |
|  | "...the floor still raked down toward where       |                     |
|  |  the screen had been, and Jones said you could     |                     |
|  |  hear it in the low end."                          |                     |
|  |                                                    |                     |
|  |                          .--------------------.    |                     |
|  |                          | STAXMUSEUM.ORG     |    |                     |
|  |                          | RET 09 AUG 2026    |    |                     |
|  |                          | FILED BY  SET      |    |                     |
|  |                          '--------------------'    |                     |
|  +----------------------------------------------------+                     |
|                                                                             |
|  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~                          |
|  | "the raked floor of the converted movie house"     |                     |
|  |                          .--------------------.    |                     |
|  |                          | ROLLINGSTONE.COM   |    |                     |
|  |                          | RET 09 AUG 2026    |    |                     |
|  |                          | FILED BY  SET      |    |                     |
|  |                          '--------------------'    |                     |
|  +----------------------------------------------------+                     |
+----------------------------------------------------------------------------+
```

### The signature element — **the stamp**

Not decoration. **The stamp only renders when the ledger check passes**, and it lands *in front of the writer* during the run. A finding arrives on screen unstamped. A beat later the stamp presses down — domain, retrieval date, the researcher's three-letter code lifted straight from `found_by`. Slightly rotated, slightly uneven ink, because that is what a rubber stamp does.

A citation that failed the ledger check gets the other pad: `UNSOURCED` in Oxide Red, angled across the clip, **and the clip stays on screen**. The claim is not deleted and not quietly dropped. It is visibly demoted.

That is the whole product argument compressed into one object, and it is the part that converts an AI-hostile screenwriter: they watch the department catch its own people, live, and nothing about it looks like a chatbot.

### How the receipts look

A receipt is a **clip** — a torn-edge fragment of Manila carrying the ledger excerpt verbatim in Newsreader italic, with the stamp block in Sligoil at 10px. Domain, not full URL, on the face; the full URL is the link target with `rel="noopener noreferrer"`. Multiple citations for one fact stack as overlapping clips, slightly offset, the way clips actually sit in a folder. Clicking any clip lifts it to the top of the stack.

The count line under each drawer reads `9 clips · 17 stamped · 0 unsourced` — three numbers, all falsifiable, none of them a confidence score.

### What it risks

- **Trap-2 drift if the cards get small.** `#232B27` is not `#0f1115`, but it is dark, and if the Manila surfaces shrink to accent-sized chips the page becomes near-black-with-a-warm-accent — the exact thing being avoided. Mitigation is a hard rule: **Manila must own more than 40% of the room's pixel area in the filed state.** The cards are the page; the cabinet is the frame.
- **The stamp can go cute.** Rotation beyond about 2.5 degrees, visible ink splatter, or a distressed texture overlay and it becomes a Photoshop filter. The stamp has to be typographic and nearly clean, with the irregularity carried in slight opacity variation and nothing else.
- **The expanded view's onionskin surface (`#E9E2D2`) is cream-adjacent.** It is a component, it appears only inside an opened drawer, and it never becomes a page ground. Break that rule and the direction lands in trap 1 by the side door.
- **Journalism, not screenwriting.** It borrows an adjacent craft's apparatus. Defensible — a studio research department did exactly this work with exactly these cabinets — but it is one step removed from the audience's own desk.

---

# Direction 2 — THE BENCH

**Thesis:** every fact is a print, and you cannot print what you have no negative for.

The inversion that makes this direction work: **the ground is the light table, illuminated.** Not a dark room with a bright accent. A cool, glowing surface with dark objects on it. A screenwriter reading a 17,000-character bible gets a light ground, which is also the humane choice.

### Why it earns the structure

Photographic provenance is the strictest consumer-grade chain that ever existed. Every frame on a contact sheet carries a machine-printed edge code that ties the print back to the exact negative it came from. The editor circles the selects in china marker — red for one pass, blue for another, and a frame nobody circled is a frame nobody vouched for.

Confirmed → circled blue. Anachronism → circled red. Unverifiable → **uncircled**. That last mapping is the best one in this entire document: *unverifiable is not a color, it is the absence of a mark*, which is exactly what unverifiable means.

### Palette

| Hex | Name | Reasoning |
|---|---|---|
| `#D9DDDE` | **Lightbox** | The illuminated table surface. A cool, faintly cyan gray-white. Not warm cream (trap 1) and not paper white. It reads as *lit from behind*, which is the whole idea. |
| `#EFF2F2` | **Hot Spot** | The brighter center of the table. Elevated reading surfaces and the expanded frame sit on it. |
| `#1C1E20` | **Rebate** | The unexposed film base at the edge of a frame. This is the near-black, and it is used as **ink and film** — type, frame borders, sprocket rails — never as a page ground. Same value that would be trap 2 as a background, entirely legitimate as an object. |
| `#585E62` | **Gray Card** | The 18% neutral reference. Secondary text, empty frames, disabled states. A photographic constant, and a deliberately non-decorative mid-tone. |
| `#2F6DB5` | **China Blue** | Grease-pencil blue. Means **filed and verified**. |
| `#E4572E` | **China Red** | Grease-pencil red. Means **flagged**. Two markers, not one accent — that is what an editor actually had on the bench, and it is what breaks the single-accent signature of trap 2. |
| `#C98B2E` | **Safelight** | The darkroom amber. Means **working**. Appears only during a run. |

### Type

- **Display — League Gothic** (The League of Moveable Type, SIL OFL, self-hostable). An Alternate Gothic revival: extremely condensed, and condensed-gothic-in-orange is literally what Kodak and Ilford printed along the rebate edge of every roll. The display face and the period reference are the same object.
- **Body — Source Serif 4** (Adobe, SIL OFL, self-hostable, variable with an `opsz` axis). Low contrast and sturdy, which matters because text sits on a light gray rather than white and a high-contrast face goes thin and shimmery there. The optical size axis carries the whole direction: this design is *captions*, and Source Serif 4's Caption cut holds at 11px in a way a single-master face does not.
- **Utility — Chivo Mono** (Omnibus-Type, SIL OFL, self-hostable). Edge codes, frame numbers, counts, timestamps. Mechanical without being a coding-font cliché.

**Why not the obvious pairing:** obvious is Inter over anything, or Space Grotesk plus a mono. League Gothic plus Source Serif 4 is a *photo-lab* pairing — signage-condensed over reading-serif — and it has the additional benefit that nobody has burned it out. Alternate display if League Gothic's single weight is too constraining in practice: **Archivo** with its width axis pushed narrow, also OFL.

### Layout — the four-quadrant room

```
+----------------------------------------------------------------------------+
| STAR                 1962 MEMPHIS  ·  1960-1962  ·  crime      [ROOM][CHECK]|
+---------+------------------------------------------------------------------+
| ROLLS   |  SETTING                        OBJECTS & PROPS                   |
|>Memphis |  .|24|.|24A|.|25|.|25A|.        .|11|.|11A|.|12|.|12A|.           |
| Noir 78 |  [==][==][==][==][  ]           [==][==][==][  ][  ]              |
| Untitled|   (O) (O) (O)                    (O) (O)     (X)                  |
|         |  9 frames · 17 negatives        8 frames · 16 negatives           |
| + NEW   |                                                                   |
|         |  LOGISTICS                      FORCES & CONFLICTS                |
|         |  .|07|.|07A|.|08|.              .|31|.|31A|.|32|.|32A|.           |
|         |  [==][==][==]                   [==][==][~~][  ]                  |
|         |   (O) (O)  ·                     (O) (O)  !                       |
|         |  6 frames · 9 negatives         5 frames · 11 negs · 1 NO NEGATIVE|
+---------+------------------------------------------------------------------+

   [==] exposed frame (a finding)      (O) circled blue  = filed
   [~~] developing (searching)         (X) circled red   = flagged
   [  ] unexposed                       !  no negative    = uncited URL
   .|24|. sprocket rail + edge code    uncircled frame    = unverifiable
```

Each quadrant is a **strip**: one frame per finding, laid on the table with the sprocket rail and edge codes running along the top. During a run, frames develop in from nothing — genuinely the right animation, and unlike a spinner it encodes *how many* are coming.

**Expanded** — the strip goes under the enlarger:

```
+----------------------------------------------------------------------------+
| <- SETTING   strip 24                    [OBJECTS][LOGISTICS][FORCES]      |
+----------------------------------------------------------------------------+
| ASKED  What did the Stax recording room look like in 1962?                  |
|                                                                             |
| .|24A|........................................................|24A|.        |
| |                                                                  |        |
| |  Stax operated out of the old Capitol Theatre; the sloped        |        |
| |  theater floor was never leveled and shaped the room's sound.    |        |
| |                                                                  |        |
| .|.....|.....|.....|.....|.....|.....|.....|.....|.....|.....|.....|        |
|                                                                             |
|   NEG 24A-1  staxmuseum.org             NEG 24A-2  rollingstone.com         |
|   "...the floor still raked down        "the raked floor of the             |
|    toward where the screen had been"     converted movie house"             |
|                                                                             |
|   (O) both negatives on file                                                |
+----------------------------------------------------------------------------+
```

### The signature element — **the edge code**

Every finding is printed film, and film carries its origin in the margin. A rebate strip runs the full edge of every finding: sprocket perforations, then a machine-set code in Chivo Mono — `24A-1 · staxmuseum.org · 09AUG26 · SET`.

The rule is absolute and stated on screen: **nothing prints without a negative.** A cited URL absent from the ledger produces a frame that is blank Gray Card with `NO NEGATIVE` set in the rebate, uncircled, sitting in the strip where the print would have been. The gap is visible. You can count it.

### How the receipts look

Two-column contact-print captions under the expanded frame. Each receipt is a small frame of its own: negative number, domain, and the ledger excerpt set in Source Serif 4 Caption italic. Clicking a receipt enlarges that negative — the excerpt goes full width with the source title above it and the outbound link on the title.

The strip footer reads `9 frames · 17 negatives · 1 no negative`. Same three falsifiable numbers as direction 1, in the language of the bench.

### What it risks

- **Light ground plus a red accent has its own cliché**, one lane over from trap 1. What holds it apart is that the ground is *cool* and there are *two* markers plus an amber state, so no single accent carries the identity. If the blue gets dropped for simplicity the direction collapses into a generic light UI with a red highlight.
- **The film metaphor can become nostalgia.** Grain overlays, vignettes, faux-scratches, a fake sprocket border on every element — any of those and it is a Instagram filter with a research tool inside. The rebate should be crisp vector, no texture at all.
- **Four strips is the weakest structural fit of the three.** A contact sheet is one roll of one subject; four strips of four different subjects is a small lie. It is a *believable* small lie — an assistant editor absolutely laid four strips on a table — but it does not have the exactness of four subject drawers.
- **Long-form reading on `#D9DDDE` needs testing.** A gray ground reduces effective contrast; Source Serif 4 at a slightly heavier weight than default compensates, but it is a real thing to check rather than assume.

---

# Direction 3 — THE ROD

**Thesis:** the card catalogue's integrity was mechanical, not clerical — a brass rod ran through every card so nothing could be added, removed, or forged, and a card off the rod is a card nobody vouches for.

### Why it earns the structure

Two conventions here are gifts.

**The rod.** Every drawer in a real card catalogue has a brass rod through the punched hole at the bottom of each card. The rod is a physical guarantee: you cannot slip a card in without opening the drawer, releasing the rod, and having the authority to do so. Provenance enforced by hardware.

**The bracket.** Archival description has a real, centuries-old convention for uncertainty: **square brackets mean the archivist supplied this, it is not in the record.** `[ca. 1962]`, `[title supplied]`, `[sic]`. It is understated, it is not a color, it never looks like an error state, and it is exactly correct for a claim STAR could not verify. Adopting it wholesale gives the product a way to be honest that reads as scholarly rather than as a warning banner.

Four trays for four subject headings is the same exact fit as the morgue's four drawers.

### Palette

| Hex | Name | Reasoning |
|---|---|---|
| `#241C17` | **Drawer Walnut** | The interior of an oak catalogue drawer. A warm near-black-brown. The third temperature in this set: direction 1 is cold dark, direction 2 is cold light, this is warm dark. Warmth is what keeps it from reading as generic dark mode. |
| `#3A2E25` | **Rail** | One step up. Trays, the sidebar, the tray-front label plates. |
| `#DCD8C8` | **Card Buff** | Standard library card stock — warm-neutral, slightly green-shifted, not white and not cream. This is the primary content surface and it should dominate the room. |
| `#8E7133` | **Brass** | The rod, and the tray pull. Deliberately duller and browner than the current `#e3b341`: this is metal under low light, not a highlight color. Means **on the rod, verified**. |
| `#8E2F39` | **Accession Red** | The oxide red of an accession stamp. Means **flagged**. Muted, not vermilion. |
| `#9A8F7C` | **Pencil** | The archivist's graphite annotations. Secondary text, and the bracketed-uncertainty type color. |

Color jobs: working = a card being typed, cursor visible. Filed = card seated, rod through it, Brass. Flagged = Accession Red. Unverifiable = brackets in Pencil, and the card sits **above** the rod line, visibly unsecured.

### Type

- **Display — Spectral SC** (Production Type, SIL OFL, self-hostable; the small-caps family ships separately from Spectral). Real small caps, which is what a catalogue heading is. Small caps at heading size gives institutional authority without the high-contrast display serif that defines trap 1 — Spectral is a low-contrast screen serif, structurally the opposite of a Didone.
- **Body — Spectral** (same family, text cuts). One family across display and body, differentiated by case and weight rather than by contrast. That is the catalogue's own discipline: one typewriter, one convention, applied consistently.
- **Utility — Courier Prime** (Quote-Unquote Apps, SIL OFL, self-hostable). Catalogue cards were *typed*, so the typed content — call numbers, dates, tracings, source lines — is genuinely a typewriter face. Courier Prime is the Courier redraw built specifically for screenplays, which flatters the audience without costume, because it is confined to the utility role and never sets a paragraph.

**Why not the obvious pairing:** obvious is Libre Caslon or Playfair over a sans, which is trap 1's exact signature. One low-contrast serif family carrying both roles, with a typewriter for anything typed, is a *system* rather than a pairing, and the small-caps discipline does the work that a display face usually does.

### Layout — the four-quadrant room

```
+----------------------------------------------------------------------------+
| STAR   CATALOGUE          1962 MEMPHIS   ·   1960-1962   ·   crime drama    |
|                           (Memphis) (Stax Studio) (McLemore Ave)           |
+---------+------------------------------------------------------------------+
| TRAYS   |  .------------------------.  .------------------------.          |
|>Memphis |  |  S E T T I N G         |  |  O B J E C T S         |          |
| Noir 78 |  |========================|  |========================|          |
| Untitled|  | ]]]]]]]]]              |  | ]]]]]]]]                |          |
|         |  |   9 cards · 17 sources |  |   8 cards · 16 sources |          |
| + NEW   |  |                        |  |                        |          |
|         |  |  o======================o  o======================o          |
|         |  '----------[ ]-----------'  '----------[ ]-----------'          |
|         |                                                                   |
|         |  .------------------------.  .------------------------.          |
|         |  |  L O G I S T I C S     |  |  F O R C E S           |          |
|         |  |========================|  |========================|          |
|         |  | ]]]]]]  (typing...)    |  | ]]]]]  ]<- off the rod  |          |
|         |  |   6 cards · 9 sources  |  |   5 cards · 11 sources |          |
|         |  |                        |  |   1 [source not located]|          |
|         |  |  o======================o  o======================o          |
|         |  '----------[ ]-----------'  '----------[ ]-----------'          |
+---------+------------------------------------------------------------------+

   ]]]]  cards seated, rod through them        o====o  the brass rod
   ]<-   card riding above the rod line        [ ]     tray pull
```

**Expanded** — the tray tips up and one card stands:

```
+----------------------------------------------------------------------------+
| <- SETTING                          [ OBJECTS ][ LOGISTICS ][ FORCES ]     |
+----------------------------------------------------------------------------+
|  ,----------------------------------------------------------------.        |
|  |  SET .24                                        09 AUG 2026     |        |
|  |                                                                  |        |
|  |  Stax operated out of the old Capitol Theatre; the sloped       |        |
|  |  theater floor was never leveled and shaped the room's sound.   |        |
|  |                                                                  |        |
|  |  ----------------------------------------------------------      |        |
|  |  1. staxmuseum.org                                               |        |
|  |     "...the floor still raked down toward where the screen       |        |
|  |      had been"                                                   |        |
|  |  2. rollingstone.com                                             |        |
|  |     "the raked floor of the converted movie house"               |        |
|  |                                                                  |        |
|  |                    o=========== rod ===========o                 |        |
|  '------------------------------o------o--------------------------'        |
|                                                                             |
|  ,----------------------------------------------------------------.        |
|  |  SET .25                                        [not located]   |        |
|  |                                                                  |        |
|  |  [The house band recorded four nights a week.]                  |        |
|  |                                                                  |        |
|  |  ----------------------------------------------------------      |        |
|  |  1. [source supplied by researcher; not located in the record]  |        |
|  |     memphisarchive.example/band-schedule                        |        |
|  '------------------------------------------------------------------'      |
|          ^ card sits above the rod line, unsecured                          |
+----------------------------------------------------------------------------+
```

### The signature element — **the rod**

A brass rod runs horizontally through every quadrant, and cards are punched onto it. Verified findings sit **on** the rod. A finding whose citation failed the ledger check floats a few pixels above the rod line with its punch hole visibly empty — it is in the drawer, it is fully readable, and it is *not secured*.

The gesture is the argument: you cannot fake a card onto the rod, and the interface shows you which cards made it.

### How the receipts look

The **tracings block** — the numbered list at the foot of a catalogue card recording every other heading the card is filed under. STAR's version: a horizontal rule, then numbered sources in Courier Prime, each one domain plus the ledger excerpt in Spectral italic. The domain is the outbound link.

Uncertainty uses brackets, not badges. An unverified fact is **wrapped in square brackets** and its tracing reads `[source supplied by researcher; not located in the record]`. No red, no warning triangle, no toast. A convention rather than an alarm — quieter than the morgue's stamp, and arguably more credible to a skeptical reader for exactly that reason.

Footer per tray: `9 cards · 17 sources · 1 not located`.

### What it risks

- **Skeuomorphic library is a real failure mode.** Warm dark brown, buff cards, and brass is two bad decisions away from a leather-bound e-reader skin from 2011. It survives only with completely flat surfaces — no gradients, no bevels, no wood texture, no drop shadows beyond a single 1px offset. The rod must be a 2px flat brass line, not a rendered cylinder.
- **It is the quietest of the three, which cuts both ways.** The bracket convention is more credible and less legible. A skeptical screenwriter skimming for thirty seconds sees the morgue's red `UNSOURCED` stamp instantly and might not notice a pair of square brackets at all. Trust that goes unnoticed does not convert anyone.
- **It shares a family with direction 1.** Both are paper-archive worlds with drawers. The mechanics are genuinely different products — a stamp is an event, a rod is a state — but they are neighbors, and if both were built you would feel the overlap.
- **Brass at `#8E7133` is still a gold.** It is duller and browner than `#e3b341`, but it is in the same family as the accent being replaced, and it needs to stay strictly a *material* — the rod and the pull, nothing else. The moment it becomes a button fill, the direction has quietly walked back into the thing it was escaping.

---

# What I would build

**THE MORGUE.**

It is the only direction where the metaphor is a description of the system rather than a costume on it. `LedgerEntry(url, title, excerpts, found_by)` *is* a clipping file, `Finding.unverified_urls` *is* the clip someone dropped in the drawer without stamping, and four subject headings *are* four drawers. Nothing has to be stretched.

It also has the strongest conversion moment. The bench's edge code and the rod's brackets are both states you can inspect; the stamp is an **event you watch happen**. A screenwriter who walked in hostile sees the department catch its own researcher, live, in the first thirty seconds. That is the argument this product has to win, and it wins it without a single word of copy.

The palette carries the lowest trap exposure of the three — cold cabinet green under warm manila, with a violet trust color no generated UI reaches for — and Newsreader over Archivo Narrow with Sligoil for the stamps is a press-room voice nobody has burned out. Build it with the 40% Manila rule enforced.
