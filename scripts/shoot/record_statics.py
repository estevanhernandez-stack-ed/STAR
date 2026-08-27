"""The static shots, recorded natively as one continuous clip with clean holds.
Free: nothing here spends a build, check or sweep. Uses the seeded session.

Order and holds (seconds):
  shot 2   intake, treatment pasted, scrolled to its opening line       8
  room     Doctor Who: Liverpool and Hamburg Special, four drawers       5
  shot 5   Logistics drawer -> minibus finding -> Beatles Bible chip     8
  shot 5b  -> Wikipedia (Beatles in Hamburg) chip                        8
  shot 6   Check the script -> draft pasted, 31 scenes in the strip      8
  shot 8   reference sweep (17 AUG) header line                          8
  shot 9   "turning it up to eleven" + "Got blisters on your fingers"   10
  shot 10  the Casbah cluster                                           10

Each beat is logged with its video timestamp so the clip can be cut by number.
"""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
VIDEO_DIR = HERE / "video"
TREATMENT = (HERE / "treatment_body.txt").read_text(encoding="utf-8")
DRAFT = (HERE / "draft.fountain").read_text(encoding="utf-8-sig").replace("\r\n", "\n")
URL = "https://star-390753828501.us-central1.run.app"
ROOM = "1fd837bdd99e"

VIDEO_DIR.mkdir(exist_ok=True)
t_start = None
marks = []

def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def mark(name: str) -> None:
    t = time.time() - t_start
    marks.append((name, t))
    log(f"  {name} @ {t:6.1f}s")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=["--window-size=1920,1080", "--window-position=0,0"])
    ctx = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        record_video_dir=str(VIDEO_DIR),
        record_video_size={"width": 1920, "height": 1080},
    )
    raw = (HERE / "session_seed.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)
    seed = parsed if isinstance(parsed, str) else raw
    ctx.add_init_script(
        "(() => { if (location.origin !== '" + URL + "') return; const s = " + seed
        + "; for (const [k, v] of Object.entries(s)) localStorage.setItem(k, v); })()"
    )
    page = ctx.new_page()
    t_start = time.time()
    page.goto(URL)
    page.wait_for_function(
        "() => document.querySelectorAll('nav[aria-label=\"Saved rooms list\"] button').length > 0",
        timeout=120_000,
    )
    page.wait_for_timeout(1500)
    mark("rail loaded")

    # shot 2
    page.locator("#treatment").fill(TREATMENT)
    page.evaluate("() => { const t = document.getElementById('treatment'); t.scrollTop = 0; t.blur(); }")
    mark("shot 2 intake pasted")
    page.wait_for_timeout(8000)

    # the room
    page.get_by_role("button", name="Doctor Who: Liverpool and Hamburg Special 1958-1962 · Aug 12,").click()
    page.get_by_role("button", name="Open the drawer: Logistics").wait_for(state="visible", timeout=30_000)
    page.wait_for_timeout(500)
    mark("room overview")
    page.wait_for_timeout(5000)

    # shot 5
    page.get_by_role("button", name="Open the drawer: Logistics").click()
    page.wait_for_timeout(800)
    page.get_by_text("beatlesbible.com RET 12 AUG 2026 FILED BY LOG 16 August 1960: Travel: Liverpool").click()
    page.evaluate(
        "() => { const p = [...document.querySelectorAll('#stage p')].find(e => e.textContent.startsWith('A British band traveling')); p.scrollIntoView({block: 'start', behavior: 'instant'}); }"
    )
    page.wait_for_timeout(300)
    mark("shot 5 minibus + beatlesbible receipt")
    page.wait_for_timeout(8000)
    page.get_by_text("en.wikipedia.org RET 12 AUG 2026 FILED BY LOG The Beatles in Hamburg -").first.click()
    page.wait_for_timeout(300)
    mark("shot 5b wikipedia receipt")
    page.wait_for_timeout(8000)

    # shot 6
    page.get_by_role("button", name="Check the script").click()
    page.wait_for_timeout(1200)
    page.evaluate(
        "(text) => { const ta = document.getElementById('scene'); ta.focus(); ta.value = text; ta.dispatchEvent(new InputEvent('input', {bubbles: true})); ta.scrollTop = 0; ta.blur(); }",
        DRAFT,
    )
    page.wait_for_timeout(400)
    page.evaluate("() => document.querySelector('label[for=\"scene\"]').scrollIntoView({block: 'start', behavior: 'instant'})")
    mark("shot 6 draft pasted, 31 scenes")
    page.wait_for_timeout(8000)

    # shot 8: reference sweep. The filed-sweeps list is fetched when Script
    # Check opens, so wait for the picker button before pressing it.
    picker = page.get_by_role("button", name="31 scenes · 75 claims · 17 AUG 2026 15:52")
    picker.wait_for(state="visible", timeout=60_000)
    picker.click()
    # textContent, not innerText: innerText applies the header's CSS
    # text-transform and comes back uppercase.
    page.wait_for_function("() => /scenes read\\./i.test(document.getElementById('check-panel').textContent)", timeout=90_000)
    page.wait_for_timeout(500)
    page.evaluate(
        "() => { const el = [...document.querySelectorAll('#check-panel p, #check-panel div, #check-panel h4')].find(e => e.children.length === 0 && /scenes read\\./.test(e.textContent)); el.scrollIntoView({block: 'start', behavior: 'instant'}); }"
    )
    mark("shot 8 sweep header 75 claims")
    page.wait_for_timeout(8000)

    # shot 9
    page.evaluate(
        "() => { const v = document.querySelectorAll('#check-panel .sweep-verdict'); v[56].closest('li, article, section, div').scrollIntoView({block: 'start', behavior: 'instant'}); }"
    )
    mark("shot 9 eleven + blisters")
    page.wait_for_timeout(10000)

    # shot 10
    page.evaluate(
        "() => { const v = document.querySelectorAll('#check-panel .sweep-verdict'); v[9].closest('li, article, section, div').scrollIntoView({block: 'start', behavior: 'instant'}); }"
    )
    mark("shot 10 casbah cluster")
    page.wait_for_timeout(10000)

    video_path = page.video.path()
    ctx.close()
    browser.close()
    (HERE / "statics_marks.txt").write_text(
        "\n".join(f"{t:6.1f}s  {name}" for name, t in marks) + "\n", encoding="utf-8"
    )
    log(f"Video written: {video_path}")
