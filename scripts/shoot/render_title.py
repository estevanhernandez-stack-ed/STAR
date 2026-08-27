"""Render title.html to a 1920x1080 PNG with the app's own vendored fonts."""
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1920, "height": 1080})
    pg.goto((HERE / "title.html").as_uri())
    pg.wait_for_timeout(800)  # let the woff2 faces load
    pg.evaluate("() => document.fonts.ready")
    pg.screenshot(path=str(HERE / "title.png"))
    b.close()
print("title.png written")
