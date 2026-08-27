"""The correction on the page itself: one live check_scene on Chapter 3
scene 1 (the Casbah scene), recorded natively. Spends ONE check.

Flow: room -> Check the script -> paste draft -> pick "CHAPTER 3: THE STOLEN
CHORD — 1" from the strip (hold 3s) -> press Check this scene -> record the
wait -> when the marked scene renders, scroll to the Casbah mark and click it
so the rail shows the verdict (hold 12s).
"""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
VIDEO_DIR = HERE / "video"
DRAFT = (HERE / "draft.fountain").read_text(encoding="utf-8-sig").replace("\r\n", "\n")
URL = "https://star-390753828501.us-central1.run.app"
SCENE_TITLE = "CHAPTER 3: THE STOLEN CHORD — 1"

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

    page.evaluate(
        "(text) => { const ta = document.getElementById('scene'); ta.focus(); ta.value = text; ta.dispatchEvent(new InputEvent('input', {bubbles: true})); ta.scrollTop = 0; ta.blur(); }",
        DRAFT,
    )
    page.wait_for_timeout(300)
    page.evaluate("() => document.querySelector('label[for=\"scene\"]').scrollIntoView({block: 'start', behavior: 'instant'})")
    mark("draft pasted, 31 scenes")
    page.wait_for_timeout(2500)

    # Pick the Casbah scene from the strip.
    page.evaluate(
        "(title) => { const b = [...document.querySelectorAll('#check-panel button')].find(b => b.textContent.includes(title)); b.click(); }",
        SCENE_TITLE,
    )
    page.wait_for_timeout(400)
    page.evaluate("() => { const ta = document.getElementById('scene'); ta.scrollTop = 0; }")
    mark("scene picked: " + SCENE_TITLE)
    page.wait_for_timeout(3000)

    marks_before = page.evaluate("() => document.querySelectorAll('#check-panel mark').length")
    run = page.get_by_role("button", name="Check this scene")
    run.click()
    mark("CHECK PRESSED")
    t0 = time.time()
    landed = False
    try:
        # The marked scene renders as <mark> elements; wait for new ones.
        page.wait_for_function(
            "(n) => document.querySelectorAll('#check-panel mark').length > n",
            arg=marks_before,
            timeout=320_000,
        )
        landed = True
    except Exception as exc:  # noqa: BLE001
        log(f"No marked scene before the ceiling: {exc.__class__.__name__}")
    t1 = time.time()
    mark(f"check {'landed' if landed else 'unfinished'} after {t1 - t0:.0f}s")
    page.wait_for_timeout(1500)

    # Find the Casbah mark, bring it into view, click it so the rail follows.
    found = page.evaluate(
        "() => { const m = [...document.querySelectorAll('#check-panel mark')].find(m => /casbah/i.test(m.textContent)); if (!m) return null; m.scrollIntoView({block: 'center', behavior: 'instant'}); return m.textContent.trim(); }"
    )
    mark(f"casbah mark: {found!r}")
    if found:
        page.wait_for_timeout(1500)
        page.evaluate(
            "() => { const m = [...document.querySelectorAll('#check-panel mark')].find(m => /casbah/i.test(m.textContent)); m.click(); }"
        )
        mark("casbah mark clicked, rail follows")
    page.wait_for_timeout(12000)

    all_marks = page.evaluate(
        "() => [...document.querySelectorAll('#check-panel mark')].map(m => m.className + ' :: ' + m.textContent.trim()).slice(0, 40)"
    )
    rail = page.evaluate(
        "() => { const r = document.querySelector('#check-panel [class*=\"rail\"]'); return r ? r.textContent.replace(/\\s+/g, ' ').trim().slice(0, 600) : null; }"
    )

    video_path = page.video.path()
    ctx.close()
    browser.close()
    (HERE / "check_marks.txt").write_text(
        "\n".join(f"{t:6.1f}s  {name}" for name, t in marks)
        + f"\ncheck_elapsed_s={t1 - t0:.1f}\nlanded={landed}\n\nMARKS:\n" + "\n".join(all_marks)
        + f"\n\nRAIL:\n{rail}\n",
        encoding="utf-8",
    )
    log(f"Video written: {video_path}")
