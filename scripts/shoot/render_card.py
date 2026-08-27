"""Render any card HTML in this folder to a 1920x1080 PNG: render_card.py end"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
name = sys.argv[1] if len(sys.argv) > 1 else "title"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1920, "height": 1080})
    pg.goto((HERE / f"{name}.html").as_uri())
    pg.wait_for_timeout(800)
    pg.evaluate("() => document.fonts.ready")
    pg.screenshot(path=str(HERE / f"{name}.png"))
    b.close()
print(f"{name}.png written")
