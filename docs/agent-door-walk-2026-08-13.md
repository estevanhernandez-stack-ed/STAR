# The agent-door walk — a prompt to hand an agent

> Paste everything below the line into Claude Desktop (or the VS Code
> extension) **with the STAR connector attached**. It is written for the agent,
> not for you.
>
> **Before you paste it: restart the desktop app.** The connector is already
> authorized and has been used against STAR before — what it will not have is
> the tools shipped since it last started. A client caches the tool list from
> its handshake, so an agent that never restarted will walk this list looking
> for `export_room` and `import_rooms` and report them missing. That would be a
> false defect, and it would look exactly like a real one.
>
> **Scope, which matters at step 7.** STAR's discovery advertises `rooms:read`,
> `rooms:write` and `rooms:delete`; the consent screen defaults to **read and
> write only** — `rooms:delete` has to be asked for by name. Whatever was
> granted on the original authorization is what the agent still holds. If
> delete was not among it, step 7 tests the refusal instead, which is the more
> useful answer anyway.
>
> **This walk spends money in exactly two places, both marked.** Everything
> else is free. Total: one editor call and one sweep, or one editor call alone
> if you skip 6b.

---

You have the STAR MCP connector attached. STAR is a screenwriter's research
tool: it builds researched "rooms" about a story's world, checks a screenplay's
claims against them, and cites what it finds.

I want you to walk its agent door end to end and report what a person would be
able to do with what came back. **This surface has never been walked by a human
or an agent.** Every other part of the app has, and seven defects turned up
today doing exactly this — so assume there are more here, and look for them.

## What I am asking you to judge

Not "did the call succeed." Every defect found today was a call that succeeded
and returned something **true and unusable**:

- a sentence that said `1 row … and were skipped`
- a confirmation whose button was three lines above the sentence asking for it
- fourteen accurate complaints, none of which said "this file is from a
  different sweep"
- an error naming an id that appears on no screen in the product

So for every step: **could a person act on what came back, without already
knowing how the system works?** If a message names an identifier, ask whether
that identifier is discoverable anywhere else. If it reports a count, ask
whether the count is the thing they needed. Say so plainly when the answer is
no, even when nothing is broken.

## Ground rules

1. **Report, do not repair.** If something looks wrong, write it down and keep
   walking. Do not edit files, do not retry with different arguments to make it
   pass, do not work around it.
2. **Spend only where marked.** Steps 6b and 8 spend. Nothing else may call
   `build_room`, `check_scene`, `research_question`, or `sweep_draft`.
3. **Never confirm a destructive call.** Step 7 asks you to find out what
   deleting would remove. Stop at the answer. Do not pass the token back.
4. **Quote what you actually saw.** Exact strings, exact numbers, exact tool
   names. If a number seems wrong, give the number rather than the impression.

## The walk

### 1. The handshake

List STAR's tools.

**Expect:** fifteen, arriving in three bands — reads, then writes that spend
nothing, then the ones that spend. The names are `list_rooms`, `get_room`,
`ask_room`, `defend_claim`, `get_sweep`, `export_room`, `link_room`,
`import_rooms`, `import_notes`, `delete_room`, `build_room`, `check_scene`,
`research_question`, `sweep_draft`, `write_bible`.

**If you were served fourteen and `import_notes` is missing, stop and say so
before going further** — it means this client never picked up the newest tool
and step 10 cannot run. Restarting the app is the fix, not a bug report.

**Report:** any name you were served that is not on that list, any on the list
you were not served, and whether the descriptions alone are enough to know
which ones cost money. The descriptions are the only documentation an agent
gets — say whether they did the job.

### 2. Reads, which cost nothing

List my rooms. Then get the summary of whichever room mentions Liverpool.

**Expect:** `list_rooms`, then `get_room` with `shape: summary`.

**Known and correct, so do not report it as a bug:** `source_count` runs to
roughly twice the number of citations in the drawers. It counts every page a
search returned; a citation is a page a researcher chose to stand a finding on.
**Do report** whether anything on the surface told you that, or whether you had
to be told by me.

### 3. Ask a room something it already knows

Ask that room a question its research would cover — something about Liverpool
in 1958.

**Expect:** `ask_room`, free, no searches spent. The answer should rest on the
room's own findings.

**Report:** whether the reply distinguishes "the room holds this" from "I know
this." That distinction is the entire product.

### 4. A citation on demand

Ask it to defend one specific claim from that room.

**Expect:** `defend_claim`, free, returning the finding with its source and the
date the source came back.

**Report:** whether you could hand that card to a fact-checker as-is.

### 5. The file half

Export that room's research. Then export it again as the whole chain.

**Expect:** `export_room`, free, defaulting to `shape: summary` — filename,
size, column names, first few rows. **A wall of CSV in the reply is a defect**;
these files run to hundreds of kilobytes.

**Report:** the exact filename. It should carry the room and the date. Then say
whether, holding two exports of the same room made an hour apart, you could
tell them apart from the filenames alone.

### 6. Import, which is armed

**6a.** Ask STAR to import a research CSV. Use the one at
`C:\Users\estev\Downloads\doctor-who-liverpool-and-hamburg-special-research-2026-08-13 (1).csv`
— read it off disk with your own file tools and pass its text.

**That file is chosen deliberately.** It holds one room, and that room's
`continues` column names a parent room that is **not in the file**. So the
import has something real to complain about, and the complaint is the thing I
want judged.

**Expect: two calls.** The first files nothing, tells you what the file holds,
and hands back a one-time token. The second files it. **Anything filed on the
first call is a defect. A token that works twice is a defect.**

**Report:** whether the first call's report was enough to decide with — how
many rooms, how many findings, and what it will do about the missing parent.
Then say whether the complaint about that parent named it in a way you could
act on, or whether it handed you a bare identifier. Then try the token a second
time and say what happened.

**6b. — THIS ONE SPENDS.** Skip if you want the walk free. Otherwise: ask it to
sweep a short scene against a room with `sweep_draft`, three or four lines of
screenplay, no more.

### 7. The destructive one, without pressing it

Ask what deleting a room would remove. **Stop at the answer.**

**Expect:** `delete_room` called once, no confirmation, reporting exactly what
the room holds and handing back a one-time token. **Nothing removed.** If
anything was removed by that first call, stop the walk and tell me immediately.

**Also report:** whether you had `rooms:delete` at all. If the consent screen
granted read and write only, this call should refuse — and the refusal should
tell you why in words a person could act on, not just a status code.

### 8. Write a bible — THIS ONE SPENDS

Write the bible for the room you imported at 6a. One editor call, no searches.

**Expect:** a bible appears, and the room still reports that it was imported
rather than researched.

**Report:** whether the room's own summary now overstates what it cost. An
imported room bought no searches, and a bible written for it does not change
that.

### 9. Link two rooms

Link the imported room to another as a continuation.

**Expect:** `link_room`, free. Afterwards a chain export should carry both,
nearest first.

**Report:** whether anything told you the link took, or whether you had to
export to find out.

### 10. The loop closes — `import_notes`

This one shipped after the rest of this walk was written, and **nothing has
ever called it**, from a browser or otherwise. Treat it as the least-trusted
tool on the door.

Export a sweep with `export_room` and `kind: sweep`. Add a `writer_note` column
to two or three rows and a `dismissed` column with `yes` on one. Send the whole
file back with the `run_id` and `sweep_id` it came from.

**Expect: two calls, like `import_rooms`.** The first files nothing and lists,
**claim by claim**, what would change — the note each takes, whether it is
struck, and the words any note replaces. The second files them.

**Report:**

- Whether the first call's list was enough to confirm from without opening the
  file again. That list is the whole reason this tool arms rather than files,
  so if it is not enough, say exactly what was missing.
- What happened when you sent the token twice.
- What happened when you sent a **different** file with the first file's token.
  Nothing should be filed.
- Now export a **different** sweep of the same room and send that file with the
  first sweep's `sweep_id`. It should be refused. Say whether the refusal told
  you which sweep to use in terms you could act on, or handed you a bare id.
- Whether a verdict, a source or an excerpt could be changed through it. They
  should not be. Try, and report what came back.

## What to report back

One list, in this order:

1. **Anything that was removed, spent, or written that I did not ask for.**
   First, always, even if the list is empty — say that it is empty.
2. **Defects**, each with the tool, the exact input, and the exact output.
3. **True but unusable**, which is the class I actually care about: calls that
   worked and still left a person with nothing to do next. Quote the message
   and say what a person could not do with it.
4. **What the tool descriptions failed to tell you** that you had to work out
   or guess.
5. **What you did not reach**, and why.

Do not summarize this as "mostly working." Give me the list.
