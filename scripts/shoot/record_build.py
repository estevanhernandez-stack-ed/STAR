"""Shot 3+4: the live build, recorded natively by Playwright (no screen recorder,
no screenshots, no flashing).

Flow:
  1. Opens a headed Chromium at 1920x1080 with video recording on.
  2. Loads STAR. Este signs in (Your card -> Google) in that window.
  3. Waits until the rail shows rooms, then waits for a GO file to appear
     (scratchpad/GO) — that is the one deliberate press that spends a build.
  4. Clicks New room, pastes the treatment, presses Build the Room.
  5. Records until the room files (header reads "N web searches · ... · filed
     DD MON YYYY") or 620s passes, holds 6s on the filed room, then closes the
     context so the .webm is flushed.

Output: scratchpad/video/<hash>.webm plus build_timing.txt with start/end.
"""
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
VIDEO_DIR = HERE / "video"
GO = HERE / "GO"
TREATMENT = (HERE / "treatment_body.txt").read_text(encoding="utf-8")
URL = "https://star-390753828501.us-central1.run.app"

VIDEO_DIR.mkdir(exist_ok=True)
if GO.exists():
    GO.unlink()

def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=["--window-size=1920,1080", "--window-position=0,0"])
    ctx = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        record_video_dir=str(VIDEO_DIR),
        record_video_size={"width": 1920, "height": 1080},
    )
    # Seed the signed-in session copied from the working Playwright window, so
    # Google's automation check never enters the picture. Runs before any page
    # script on the STAR origin.
    seed_path = HERE / "session_seed.json"
    if seed_path.exists():
        raw = seed_path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        # The MCP saved the evaluate result JSON-encoded, so the file may hold a
        # string containing JSON rather than the object itself. Accept both.
        seed = parsed if isinstance(parsed, str) else raw
        ctx.add_init_script(
            "(() => { if (location.origin !== '" + URL + "') return; "
            "const s = " + seed + "; "
            "for (const [k, v] of Object.entries(s)) localStorage.setItem(k, v); })()"
        )
        log("Session seed loaded.")
    page = ctx.new_page()
    page.goto(URL)
    log("STAR loaded. Waiting for rooms in the rail...")

    # Wait for the rail to show a real room title (sign-in landed).
    # Poll rather than wait_for_function: the Google redirect destroys the
    # execution context, and a fixed timeout closed the window once already.
    while True:
        try:
            n = page.evaluate(
                "() => [...document.querySelectorAll('nav[aria-label=\"Saved rooms list\"] button')].length"
            )
            if n and n > 0:
                break
        except Exception:  # noqa: BLE001 - mid-navigation, try again
            pass
        time.sleep(2)
    log("Rooms in the rail. Waiting for GO file...")
    while not GO.exists():
        time.sleep(1)
    GO.unlink()
    log("GO. Opening a new room and pasting the treatment.")

    page.get_by_role("button", name="New room").click()
    page.wait_for_timeout(1500)
    box = page.locator("#treatment")
    box.fill(TREATMENT)
    page.evaluate("() => { const t = document.getElementById('treatment'); t.scrollTop = 0; }")
    page.wait_for_timeout(4000)  # hold on the pasted treatment (shot 2, live)

    t0 = time.time()
    page.get_by_role("button", name="Build the Room").click()
    log("Build pressed. Recording until the room files (<= 620s).")

    filed = False
    try:
        page.wait_for_function(
            "() => /\\d+ web searches · \\d+ sources returned · filed \\d+ [A-Z]{3} \\d{4}/.test(document.body.innerText)",
            timeout=620 * 1000,
        )
        filed = True
    except Exception as exc:  # noqa: BLE001 - we want the recording regardless
        log(f"Did not see a filed header before the ceiling: {exc.__class__.__name__}")
    t1 = time.time()
    log(f"Build {'filed' if filed else 'unfinished'} after {t1 - t0:.0f}s. Holding 6s on the result.")
    page.wait_for_timeout(6000)

    (HERE / "build_timing.txt").write_text(
        f"pressed={t0:.3f}\nended={t1:.3f}\nelapsed_s={t1 - t0:.1f}\nfiled={filed}\n", encoding="utf-8"
    )
    video_path = page.video.path()
    ctx.close()
    browser.close()
    log(f"Video written: {video_path}")
