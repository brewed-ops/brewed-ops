"""Screenshot both banners as GitHub shows them (<img> at README width) at several loop times.

Run:  python scripts/preview.py [out_dir]   (default: preview/, git-ignored)
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "preview"
TIMES = [1.2, 3.0, 5.6, 11.6]  # mid-typing, half, full log, fading out
PAGE_BG = {"dark": "#0d1117", "light": "#ffffff"}  # GitHub page colours

OUT.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")  # system Chrome, no bundled download
    for theme, bg in PAGE_BG.items():
        page = browser.new_page(viewport={"width": 880, "height": 420}, device_scale_factor=2)
        svg = (ROOT / "assets" / f"banner-{theme}.svg").as_uri()
        html = OUT / f"_page-{theme}.html"
        html.write_text(f'<body style="margin:0;padding:20px;background:{bg}"><img src="{svg}" style="width:840px;display:block"></body>')
        page.goto(html.as_uri(), wait_until="load")  # SVG clock starts at load
        start = 0.0
        for t in TIMES:
            page.wait_for_timeout(int((t - start) * 1000))
            start = t
            page.screenshot(path=str(OUT / f"{theme}-{t:04.1f}s.png"))
        page.close()
    browser.close()
print(f"wrote {len(TIMES) * len(PAGE_BG)} shots to {OUT}")
