"""Screenshot an animated README SVG as GitHub shows it (<img> at README width) at several loop times.

Run:  python scripts/preview.py [out_dir] [--svg talker]   (default: preview/, git-ignored; default svg: banner)
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
NAME = sys.argv[sys.argv.index("--svg") + 1] if "--svg" in sys.argv else "banner"
ARGS = [a for a in sys.argv[1:] if a not in ("--svg", NAME)]
OUT = Path(ARGS[0]) if ARGS else ROOT / "preview"
TIMES = {"banner": [1.2, 3.0, 5.6, 11.6],         # mid-typing, half, full log, fading out
         "talker": [2.0, 7.4, 9.6, 14.2, 19.6]}[NAME]  # mid line 1, then each next line
HEIGHT = {"banner": 420, "talker": 350}[NAME]
PAGE_BG = {"dark": "#0d1117", "light": "#ffffff"}  # GitHub page colours

OUT.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")  # system Chrome, no bundled download
    for theme, bg in PAGE_BG.items():
        page = browser.new_page(viewport={"width": 880, "height": HEIGHT}, device_scale_factor=2)
        svg = (ROOT / "assets" / f"{NAME}-{theme}.svg").as_uri()
        html = OUT / f"_page-{NAME}-{theme}.html"
        html.write_text(f'<body style="margin:0;padding:20px;background:{bg}"><img src="{svg}" style="width:840px;display:block"></body>')
        page.goto(html.as_uri(), wait_until="load")  # SVG clock starts at load
        start = 0.0
        for t in TIMES:
            page.wait_for_timeout(int((t - start) * 1000))
            start = t
            page.screenshot(path=str(OUT / f"{NAME}-{theme}-{t:04.1f}s.png"))
        page.close()
    browser.close()
print(f"wrote {len(TIMES) * len(PAGE_BG)} shots to {OUT}")
