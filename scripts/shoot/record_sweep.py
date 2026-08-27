"""Shot 7: the live sweep, recorded natively. Spends ONE sweep against the
hourly limit. Uses the seeded session.

Flow: open room 1fd837bdd99e -> Check the script -> paste the 31-scene draft
(hold 4s) -> press Sweep the whole draft -> record the wait until a new sweep
appears in the picker or 320s pass -> scroll to the result header, hold 8s.
"""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
VIDEO_DIR = HERE / "video"
DRAFT = (HERE / "draft.fountain").read_text(encoding="utf-8-sig").replace("\r\n", "\n")
URL = "https://star-390753828501.us-central1.run.app"

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
    page.wait_for_timeout(1000)

    page.get_by_role("button", name="Doctor Who: Liverpool and Hamburg Special 1958-1962 · Aug 12,").click()
    page.get_by_role("button", name="Open the drawer: Logistics").wait_for(state="visible", timeout=30_000)
    page.get_by_role("button", name="Check the script").click()
    page.wait_for_timeout(1200)
    # Let the filed-sweeps list arrive so the picker count is known before we spend.
    page.get_by_role("button", name="31 scenes · 75 claims · 17 AUG 2026 15:52").wait_for(state="visible", timeout=60_000)
    before = page.evaluate(
        "() => [...document.querySelectorAll('#check-panel button')].filter(b => /scenes · \\d+ claims ·/.test(b.textContent)).length"
    )
    mark(f"check surface open, {before} sweeps in picker")

    page.evaluate(
        "(text) => { const ta = document.getElementById('scene'); ta.focus(); ta.value = text; ta.dispatchEvent(new InputEvent('input', {bubbles: true})); ta.scrollTop = 0; ta.blur(); }",
        DRAFT,
    )
    page.wait_for_timeout(300)
    page.evaluate("() => document.querySelector('label[for=\"scene\"]').scrollIntoView({block: 'start', behavior: 'instant'})")
    mark("draft pasted, 31 scenes")
    page.wait_for_timeout(4000)

    page.get_by_role("button", name="Sweep the whole draft").click()
    mark("SWEEP PRESSED")
    t0 = time.time()
    landed = False
    try:
        page.wait_for_function(
            "(before) => [...document.querySelectorAll('#check-panel button')].filter(b => /scenes · \\d+ claims ·/.test(b.textContent)).length > before",
            arg=before,
            timeout=320_000,
        )
        landed = True
    except Exception as exc:  # noqa: BLE001
        log(f"No new sweep in the picker before the ceiling: {exc.__class__.__name__}")
    t1 = time.time()
    mark(f"sweep {'landed' if landed else 'unfinished'} after {t1 - t0:.0f}s")
    page.wait_for_timeout(2500)
    try:
        page.evaluate(
            "() => { const el = [...document.querySelectorAll('#check-panel p, #check-panel div, #check-panel h4')].find(e => e.children.length === 0 && /scenes read\\./i.test(e.textContent)); if (el) el.scrollIntoView({block: 'start', behavior: 'instant'}); }"
        )
    except Exception:  # noqa: BLE001
        pass
    mark("result header")
    page.wait_for_timeout(8000)

    video_path = page.video.path()
    ctx.close()
    browser.close()
    (HERE / "sweep_marks.txt").write_text(
        "\n".join(f"{t:6.1f}s  {name}" for name, t in marks) + f"\nsweep_elapsed_s={t1 - t0:.1f}\nlanded={landed}\n",
        encoding="utf-8",
    )
    log(f"Video written: {video_path}")
