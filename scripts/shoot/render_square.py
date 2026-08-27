"""Render a card HTML at a square size: render_square.py icon 1024"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
name = sys.argv[1]
size = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": size, "height": size})
    pg.goto((HERE / f"{name}.html").as_uri())
    pg.wait_for_timeout(800)
    pg.evaluate("() => document.fonts.ready")
    pg.screenshot(path=str(HERE / f"{name}-{size}.png"))
    b.close()
print(f"{name}-{size}.png written")
