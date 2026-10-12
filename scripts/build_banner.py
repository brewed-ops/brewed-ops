"""Build the animated profile banner for github.com/brewed-ops.

Run:  python scripts/build_banner.py
Out:  assets/banner-dark.svg, assets/banner-light.svg

GitHub shows README images through <img>, which blocks external fonts and images,
so the fonts are subset to the exact glyphs used and embedded with the mark as data URIs.
Edit CONTENT below, rerun, commit.
"""
import base64
import io
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OUT = ROOT / "assets"

# ---- content -------------------------------------------------------------
LABEL = "BREWEDOPS  /  PHILIPPINES  /  UTC+8"
HEAD_1 = "Automations and apps,"
HEAD_2_ACCENT, HEAD_2_REST = "brewed", " to perfection."
SUB = "Kenneth Villar  ·  Certified GHL Admin  ·  builds with AI"
LOG = [  # (tag, name, status) - status None = blinking cursor line
    ("ghl", "client automations", "live"),
    ("app", "kapevault", "shipped"),
    ("skill", "canvas-skills", "shipped"),
    ("tpl", "portfolio-template", "public"),
    ("next", "a useless app, probably", None),
]

# ---- themes (brewedops.com tokens) ----------------------------------------
THEMES = {
    "dark": dict(bg="#0f0f10", card="#161618", border="#f2efe91a", fg="#f2efe9", fg2="#c9c2b6",
                 muted="#f2efe97a", accent="#6f9be0", green="#51af43", dot="#f2efe9",
                 mark="brewedops-mark.png"),
    "light": dict(bg="#f2efe9", card="#faf8f4", border="#0f0f101f", fg="#0f0f10", fg2="#4a4a4d",
                  muted="#0f0f1080", accent="#004aac", green="#2f7d25", dot="#0f0f10",
                  mark="brewedops-mark-ink.png"),
}

FONTS = {"head": "poppins-600-latin.woff2", "body": "poppins-400-latin.woff2",
         "mono": "jetbrains-mono-latin.woff2"}

W, H = 1200, 400
LOOP = 12  # seconds per brew cycle
SPRING = "cubic-bezier(.34,1.56,.64,1)"

# ---- layout ----------------------------------------------------------------
LX = 64                                  # left block x
CX, CY, CW, CH = 744, 56, 392, 288       # console card
TAG_X, NAME_X, STATUS_X = CX + 24, CX + 86, CX + CW - 24
LINE_Y0, LINE_STEP = CY + 92, 40
SIZES = dict(label=14, head=52, sub=19, mono=15)


def text_width(font: TTFont, text: str, size: float, tracking: float = 0) -> float:
    cmap, hmtx = font.getBestCmap(), font["hmtx"]
    upm = font["head"].unitsPerEm
    return sum(hmtx[cmap[ord(c)]][0] for c in text) * size / upm + tracking * len(text)


def font_face(name: str, file: str, chars: str) -> str:
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga"]
    font = subset.load_font(str(SRC / file), opts)
    sub = subset.Subsetter(opts)
    sub.populate(text=chars)
    sub.subset(font)
    buf = io.BytesIO()
    subset.save_font(font, buf, opts)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"@font-face{{font-family:'{name}';src:url(data:font/woff2;base64,{b64}) format('woff2')}}"


def mark_uri(file: str, height: int = 64) -> str:
    img = Image.open(SRC / file)
    img = img.resize((round(img.width * height / img.height), height), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def pct(seconds: float) -> str:
    return f"{seconds / LOOP * 100:.2f}%"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;")


def build(theme: str) -> str:
    t = THEMES[theme]
    fonts = {k: TTFont(SRC / f) for k, f in FONTS.items()}
    mono_text = LABEL + "brew.log" + "brewing" + "".join(a + b + (c or "") for a, b, c in LOG)
    faces = (font_face("BO Head", FONTS["head"], HEAD_1 + HEAD_2_ACCENT + HEAD_2_REST)
             + font_face("BO Body", FONTS["body"], SUB)
             + font_face("BO Mono", FONTS["mono"], mono_text))

    head_w = max(text_width(fonts["head"], HEAD_1, SIZES["head"]),
                 text_width(fonts["head"], HEAD_2_ACCENT + HEAD_2_REST, SIZES["head"]))
    sub_w = text_width(fonts["body"], SUB, SIZES["sub"])
    assert LX + max(head_w, sub_w) < CX - 24, f"left block overlaps console: {head_w:.0f}/{sub_w:.0f}px"

    keyframes, lines = [], []
    for i, (tag, name, status) in enumerate(LOG):
        y = LINE_Y0 + i * LINE_STEP
        t_in = 0.6 + i * 0.85
        keyframes.append(
            f"@keyframes ln{i}{{0%,{pct(t_in)}{{opacity:0;transform:translateY(10px);animation-timing-function:{SPRING}}}"
            f"{pct(t_in + .5)},90%{{opacity:1;transform:none}}94%,100%{{opacity:0;transform:none}}}}"
            f".ln{i}{{animation:ln{i} {LOOP}s infinite}}")
        row = (f'<text x="{TAG_X}" y="{y}" class="m tag">{esc(tag)}</text>'
               f'<text x="{NAME_X}" y="{y}" class="m name">{esc(name)}</text>')
        if status:
            t_st = t_in + .35
            keyframes.append(
                f"@keyframes st{i}{{0%,{pct(t_st)}{{opacity:0;transform:scale(.6)}}"
                f"{pct(t_st + .35)},90%{{opacity:1;transform:none}}94%,100%{{opacity:0}}}}"
                f".st{i}{{animation:st{i} {LOOP}s {SPRING} infinite}}")
            row += f'<text x="{STATUS_X}" y="{y}" class="m ok st st{i}" text-anchor="end">{esc(status)}</text>'
        else:
            cx = NAME_X + text_width(fonts["mono"], name, SIZES["mono"]) + 6
            row += f'<rect class="cur" x="{cx:.1f}" y="{y - 13}" width="9" height="17" rx="1"/>'
        lines.append(f'<g class="ln ln{i}">{row}</g>')

    bar_y = LINE_Y0 + (len(LOG) - 1) * LINE_STEP + 22
    css = f"""{faces}
.m{{font-family:'BO Mono',ui-monospace,monospace;font-size:{SIZES['mono']}px}}
.label{{font-family:'BO Mono',ui-monospace,monospace;font-size:{SIZES['label']}px;letter-spacing:2px;fill:{t['muted']}}}
.head{{font-family:'BO Head',sans-serif;font-size:{SIZES['head']}px;fill:{t['fg']};letter-spacing:-1px}}
.acc{{fill:{t['accent']}}}
.sub{{font-family:'BO Body',sans-serif;font-size:{SIZES['sub']}px;fill:{t['fg2']}}}
.tag{{fill:{t['muted']}}}.name{{fill:{t['fg']}}}.ok{{fill:{t['green']}}}.hdr{{fill:{t['fg2']}}}
.ln,.st{{transform-box:fill-box;transform-origin:left center}}.st{{transform-origin:right center}}
.cur{{fill:{t['accent']};animation:blink 1s steps(1) infinite}}
@keyframes blink{{50%{{opacity:0}}}}
.pulse{{fill:{t['green']};transform-box:fill-box;transform-origin:center;animation:pulse 1.6s ease-in-out infinite}}
@keyframes pulse{{50%{{opacity:.35;transform:scale(.7)}}}}
.bar{{fill:{t['green']};transform-box:fill-box;transform-origin:left center;animation:bar {LOOP}s linear infinite}}
@keyframes bar{{0%{{transform:scaleX(0)}}{pct(0.6 + len(LOG) * 0.85)}{{transform:scaleX(1)}}90%{{transform:scaleX(1);opacity:1}}94%,100%{{transform:scaleX(1);opacity:0}}}}
{''.join(keyframes)}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="BrewedOps - Automations and apps, brewed to perfection. Kenneth Villar, Certified GHL Admin.">
<title>BrewedOps - Kenneth Villar</title>
<defs>
<style>{css}</style>
<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="12" cy="12" r="1" fill="{t['dot']}"/></pattern>
<linearGradient id="fade" x1="0" x2="1"><stop offset=".3" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff" stop-opacity=".09"/></linearGradient>
<mask id="dotmask"><rect width="{W}" height="{H}" fill="url(#fade)"/></mask>
<clipPath id="cardclip"><rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="24"/></clipPath>
</defs>
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="24" fill="{t['bg']}" stroke="{t['border']}" stroke-width="2"/>
<rect width="{W}" height="{H}" fill="url(#dots)" mask="url(#dotmask)" clip-path="url(#cardclip)"/>
<image href="{mark_uri(t['mark'])}" x="{LX}" y="62" height="30" width="30"/>
<text x="{LX + 44}" y="83" class="label">{esc(LABEL)}</text>
<text x="{LX - 3}" y="182" class="head">{esc(HEAD_1)}</text>
<text x="{LX - 3}" y="246" class="head"><tspan class="acc">{HEAD_2_ACCENT}</tspan>{esc(HEAD_2_REST)}</text>
<text x="{LX}" y="304" class="sub">{esc(SUB)}</text>
<rect x="{CX}" y="{CY}" width="{CW}" height="{CH}" rx="16" fill="{t['card']}" stroke="{t['border']}" stroke-width="1.5"/>
<text x="{CX + 24}" y="{CY + 31}" class="m hdr">brew.log</text>
<circle class="pulse" cx="{STATUS_X - 72}" cy="{CY + 26}" r="4"/>
<text x="{STATUS_X}" y="{CY + 31}" class="m ok" text-anchor="end">brewing</text>
<line x1="{CX}" x2="{CX + CW}" y1="{CY + 50}" y2="{CY + 50}" stroke="{t['border']}" stroke-width="1.5"/>
{''.join(lines)}
<rect x="{TAG_X}" y="{bar_y}" width="{STATUS_X - TAG_X}" height="2" rx="1" fill="{t['border']}"/>
<rect class="bar" x="{TAG_X}" y="{bar_y}" width="{STATUS_X - TAG_X}" height="2" rx="1"/>
</svg>
"""


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name in THEMES:
        svg = build(name)
        path = OUT / f"banner-{name}.svg"
        path.write_text(svg, encoding="utf-8")
        print(f"{path.relative_to(ROOT)}  {len(svg) / 1024:.1f} KB")
