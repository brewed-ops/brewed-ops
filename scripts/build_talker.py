"""Build the talking mascot strip for the profile README: the cartoon presenter says a few lines in a pixel speech
bubble, with real lip sync (the talking-explainer engine's viseme rules), words typed in as they are said, and blinks.

Run:      python scripts/build_talker.py              (uses the cached timings in src/talker/timing.json)
Re-voice: python scripts/build_talker.py --voice      (edit LINES first; Windows TTS + faster-whisper, ~1 min)
Import:   python scripts/build_talker.py --import <talking-explainer>/assets/mascot   (refresh the sprites)
Out:      assets/talker-dark.svg, assets/talker-light.svg

Same <img> rules as build_banner.py: fonts subset + embedded, sprites embedded as data URIs, CSS keyframes only.
"""
import base64
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_banner import THEMES, esc, font_face, text_width  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
TK = SRC / "talker"
OUT = ROOT / "assets"

# ---- content -------------------------------------------------------------
LINES = [  # what he says; ACCENT words are drawn in the accent colour
    "Hey, I'm Kenneth. The cartoon one. Yes, I talk now.",
    "New skill: talking-explainer.",
    "Give it a topic and your voice, and I explain it on video.",
    "It's free. Grab it right below.",
]
ACCENT = {"talking-explainer."}
POSE = "wave"           # waves hello with the far hand, so the bubble tail reaches his head; has blink + mouth fit
PIXEL_FONT = "Silkscreen-Regular.ttf"
GAP = 1.1               # seconds of quiet after each line
FPS = 15                # the engine's mouth rate

W, H = 1200, 300
U = 6                                   # one bubble pixel
BX, BY, BC, BR = 282, 36, 140, 26       # bubble left/top in px, size in cells
TAIL = 6                                # tail steps (2 cells each); tip = BX - 2 * TAIL * U
TEXT_X, TEXT_LH, TEXT_SIZE = BX + 5 * U, 46, 30
FIG_H, FIG_X, FIG_FLOOR = 246, 64, 282  # mascot height, left, feet line


# ---- sprites ---------------------------------------------------------------
def import_sprites(mascot: Path) -> None:
    """Copy the pose, its blink eye patch and its six mouths at 2x display size."""
    TK.mkdir(parents=True, exist_ok=True)
    fit = json.loads((mascot / "mouth-fit.json").read_text())[POSE]
    pose = Image.open(mascot / f"poses/{POSE}.png").convert("RGBA")
    blink = Image.open(mascot / f"poses/{POSE}-blink.png").convert("RGBA")
    k = FIG_H * 2 / pose.height
    sz = lambda im: im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)  # noqa: E731
    sz(pose).save(TK / "pose.png")
    from PIL import ImageChops
    box = ImageChops.difference(pose.convert("RGB"), blink.convert("RGB")).getbbox()  # RGB: alpha never differs
    sz(blink.crop(box)).save(TK / "blink.png")
    for m in ("closed", "small", "open", "wide", "round", "fv"):
        sz(Image.open(mascot / f"mouths/{POSE}/{m}.png").convert("RGBA")).save(TK / f"mouth-{m}.png")
    geo = {"k": k, "mouth": [fit["x"] * k, fit["y"] * k], "blink": [box[0] * k, box[1] * k]}
    (TK / "geo.json").write_text(json.dumps(geo, indent=1))
    print("sprites ->", TK)


def uri(path: Path) -> str:
    im = Image.open(path).convert("RGBA").quantize(256, method=Image.Quantize.FASTOCTREE)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ---- voice -> word times + visemes ---------------------------------------
def visemes(x: np.ndarray) -> list:
    """build-presenter.py's rules, verbatim (16 kHz mono in, one viseme per 1/FPS s out)."""
    mh = int(16000 / FPS); mn = len(x) // mh
    win = np.hanning(1024).astype(np.float32); freqs = np.fft.rfftfreq(1024, 1 / 16000)
    m_rms, cen, hf = np.zeros(mn), np.zeros(mn), np.zeros(mn)
    for i in range(mn):
        c = i * mh + mh // 2
        seg = x[max(0, c - 512): c + 512]
        if len(seg) < 1024: seg = np.pad(seg, (0, 1024 - len(seg)))
        sp = np.abs(np.fft.rfft(seg * win)) ** 2; tot = sp.sum() + 1e-12
        m_rms[i] = np.sqrt((x[i * mh:(i + 1) * mh] ** 2).mean())
        cen[i] = (sp * freqs).sum() / tot; hf[i] = sp[freqs > 3500].sum() / tot
    lv = np.clip(m_rms / (np.percentile(m_rms, 95) + 1e-9), 0, 1); voiced = lv > 0.1
    c30, c70, h80 = np.percentile(cen[voiced], 30), np.percentile(cen[voiced], 70), np.percentile(hf[voiced], 80)
    vis = []
    for i in range(mn):
        if not voiced[i]:
            j = i
            while j < mn and not voiced[j]: j += 1
            k = i
            while k > 0 and not voiced[k - 1]: k -= 1
            vis.append("rest" if (j - k) >= 4 else "closed")
        elif hf[i] > h80 and lv[i] < 0.55: vis.append("fv")
        elif lv[i] < 0.3: vis.append("small")
        elif cen[i] < c30: vis.append("round")
        elif cen[i] > c70: vis.append("wide")
        else: vis.append("open")
    for i in range(1, mn - 1):
        if vis[i - 1] == vis[i + 1] != vis[i] and vis[i] != "closed": vis[i] = vis[i - 1]
    return vis


def voice() -> None:
    from faster_whisper import WhisperModel
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    model = WhisperModel("medium", device="cpu", compute_type="int8")
    tmp = Path(tempfile.mkdtemp())
    out = []
    for n, line in enumerate(LINES):
        spoken = line.replace("-", " ")
        wav = tmp / f"l{n}.wav"
        ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.SelectVoice('Microsoft David Desktop'); $s.SetOutputToWaveFile('{wav}'); "
              f"$s.Speak('{spoken.replace(chr(39), chr(39) * 2)}'); $s.Dispose()")
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], check=True)
        sr, x = wavfile.read(wav)
        x = x.astype(np.float32) / 32768.0
        if x.ndim > 1: x = x.mean(axis=1)
        x = resample_poly(x, 16000, sr).astype(np.float32)
        segs, _ = model.transcribe(str(wav), language="en", word_timestamps=True, initial_prompt=spoken)
        heard = [w.start for s in segs for w in s.words]
        tokens = line.split()
        need = [len(t.replace("-", " ").split()) for t in tokens]
        if len(heard) == sum(need):  # each shown token starts on its first spoken word
            idx = np.cumsum([0] + need[:-1])
            starts = [heard[i] for i in idx]
        else:  # whisper split differently: spread by character position
            print(f"line {n}: heard {len(heard)} words for {sum(need)}, timing by characters")
            t0, t1, pos = heard[0], heard[-1], 0
            starts = []
            for t in tokens:
                starts.append(t0 + (t1 - t0) * pos / len(line)); pos += len(t) + 1
        out.append({"line": line, "starts": [round(s, 3) for s in starts],
                    "dur": round(len(x) / 16000, 3), "vis": visemes(x)})
        print(f"line {n}: {out[-1]['dur']}s  {len(tokens)} words")
    (TK / "timing.json").write_text(json.dumps(out, indent=1))


# ---- bubble: a pixel shape from grid cells -------------------------------
def bubble_cells() -> set:
    cells = {(c, r) for c in range(BC) for r in range(BR)}
    for c, r in [(0, 0), (1, 0), (0, 1)]:  # stepped corners
        for cc, rr in [(c, r), (BC - 1 - c, r), (c, BR - 1 - r), (BC - 1 - c, BR - 1 - r)]:
            cells.discard((cc, rr))
    for i in range(TAIL):  # tail: steps down-left until it touches his head
        for c in range(-(i + 1) * 2, 0):
            cells.add((c, 9 + i))
    return cells


def runs(cells: set, dx: float = 0, dy: float = 0) -> str:
    """Merge each row of cells into rects."""
    out = []
    for r in sorted({r for _, r in cells}):
        cols = sorted(c for c, rr in cells if rr == r)
        start = prev = cols[0]
        for c in cols[1:] + [None]:
            if c is not None and c == prev + 1:
                prev = c; continue
            out.append(f'<rect x="{BX + start * U + dx}" y="{BY + r * U + dy}" width="{(prev - start + 1) * U}" height="{U}"/>')
            if c is not None: start = prev = c
    return "".join(out)


# ---- svg -------------------------------------------------------------------
def build(theme: str, timing: list) -> str:
    t = THEMES[theme]
    geo = json.loads((TK / "geo.json").read_text())
    font = TTFont(SRC / PIXEL_FONT)
    face = font_face("BO Pixel", PIXEL_FONT, "".join(LINES))

    # timeline: line n starts at T[n]; the loop is every line + its gap
    T, acc = [], 0.4
    for ln in timing:
        T.append(acc); acc += ln["dur"] + GAP
    LOOP = round(acc, 2)
    pc = lambda s: f"{max(0, min(s, LOOP)) / LOOP * 100:.3f}%"  # noqa: E731

    css, words = [], []
    fill = bubble_cells()
    outline = {(c + dc, r + dr) for c, r in fill for dc in (-1, 0, 1) for dr in (-1, 0, 1)} - fill
    for n, ln in enumerate(timing):
        tokens = ln["line"].split()
        x, row, placed = TEXT_X, 0, []
        for tok in tokens:  # wrap first, so the block can be centred in the bubble
            w = text_width(font, tok, TEXT_SIZE)
            if x + w > BX + BC * U - 5 * U:
                x, row = TEXT_X, row + 1
            placed.append((x, row)); x += w + text_width(font, " ", TEXT_SIZE)
        assert row <= 1, f"line {n} needs {row + 1} rows: shorten it or widen the bubble"
        y0 = BY + (BR * U - (row + 1) * TEXT_LH) / 2 + TEXT_LH * 0.72
        end = T[n] + ln["dur"] + GAP - 0.15
        for i, (tok, st, (x, r)) in enumerate(zip(tokens, ln["starts"], placed)):
            name = f"w{n}_{i}"
            on = T[n] + st - 0.04
            css.append(f"@keyframes {name}{{0%{{opacity:0}}{pc(on)}{{opacity:1}}{pc(end)}{{opacity:0}}}}"
                       f".{name}{{opacity:0;animation:{name} {LOOP}s step-end infinite}}")
            cls = "px acc" if tok in ACCENT else "px"
            words.append(f'<text x="{x:.1f}" y="{y0 + r * TEXT_LH:.1f}" class="{cls} {name}">{esc(tok)}</text>')

    # mouths: each shape is on only while its viseme plays ("rest" = the pose's own drawn mouth)
    on_at = {m: [] for m in ("closed", "small", "open", "wide", "round", "fv")}
    for n, ln in enumerate(timing):
        for i, v in enumerate(ln["vis"]):
            if v != "rest": on_at[v].append(T[n] + i / FPS)
    mouths = []
    for m, times in on_at.items():
        stops, prev = ["0%{opacity:0}"], None
        for s in times:
            if prev is None or s - prev > 1.5 / FPS:
                if prev is not None: stops.append(f"{pc(prev + 1 / FPS)}{{opacity:0}}")
                stops.append(f"{pc(s)}{{opacity:1}}")
            prev = s
        if prev is not None: stops.append(f"{pc(prev + 1 / FPS)}{{opacity:0}}")
        css.append(f"@keyframes m{m}{{{''.join(stops)}}}.m{m}{{opacity:0;animation:m{m} {LOOP}s step-end infinite}}")
        mouths.append((m, f"m{m}"))

    # blinks at quiet moments: in each gap, plus one mid-loop
    blinks = [T[n] + timing[n]["dur"] + 0.35 for n in range(len(timing))]
    stops = ["0%{opacity:0}"] + [f"{pc(b)}{{opacity:1}}{pc(b + 0.13)}{{opacity:0}}" for b in blinks]
    css.append(f"@keyframes blink{{{''.join(stops)}}}.blink{{opacity:0;animation:blink {LOOP}s step-end infinite}}")

    # sprites are stored at 2x display size
    pose = Image.open(TK / "pose.png")
    fw, fh = pose.width / 2, pose.height / 2
    fx, fy = FIG_X, FIG_FLOOR - fh
    mx, my = geo["mouth"][0] / 2, geo["mouth"][1] / 2
    bx_, by_ = geo["blink"][0] / 2, geo["blink"][1] / 2
    mw = lambda p: Image.open(p).width / 2  # noqa: E731
    mh = lambda p: Image.open(p).height / 2  # noqa: E731

    imgs = [f'<image href="{uri(TK / "pose.png")}" x="0" y="0" width="{fw:.1f}" height="{fh:.1f}"/>',
            f'<image class="blink" href="{uri(TK / "blink.png")}" x="{bx_:.1f}" y="{by_:.1f}" '
            f'width="{mw(TK / "blink.png"):.1f}" height="{mh(TK / "blink.png"):.1f}"/>']
    for m, cls in mouths:
        p = TK / f"mouth-{m}.png"
        imgs.append(f'<image class="{cls}" href="{uri(p)}" x="{mx:.1f}" y="{my:.1f}" width="{mw(p):.1f}" height="{mh(p):.1f}"/>')

    style = f"""{face}
.px{{font-family:'BO Pixel',monospace;font-size:{TEXT_SIZE}px;fill:{t['fg']}}}.acc{{fill:{t['accent']}}}
.ink{{fill:{t['fg']}}}.paper{{fill:{t['card']}}}.drop{{fill:{t['fg']};opacity:.12}}
{''.join(css)}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}[class*=w0_]{{opacity:1!important}}}}"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="A cartoon of Kenneth talking in a pixel speech bubble: {esc(' '.join(LINES))}">
<title>{esc(' '.join(LINES))}</title>
<defs>
<style>{style}</style>
<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="12" cy="12" r="1" fill="{t['dot']}"/></pattern>
<linearGradient id="fade" x1="1" x2="0"><stop offset=".3" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff" stop-opacity=".09"/></linearGradient>
<mask id="dotmask"><rect width="{W}" height="{H}" fill="url(#fade)"/></mask>
<clipPath id="cardclip"><rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="24"/></clipPath>
</defs>
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="24" fill="{t['bg']}" stroke="{t['border']}" stroke-width="2"/>
<rect width="{W}" height="{H}" fill="url(#dots)" mask="url(#dotmask)" clip-path="url(#cardclip)"/>
<ellipse cx="{fx + fw * 0.45:.1f}" cy="{FIG_FLOOR - 2}" rx="{fw * 0.42:.1f}" ry="7" class="ink" opacity=".10"/>
<g transform="translate({fx:.1f} {fy:.1f})">{''.join(imgs)}</g>
<g class="drop">{runs(fill | outline, U, U)}</g>
<g class="ink">{runs(outline)}</g>
<g class="paper">{runs(fill)}</g>
{''.join(words)}
</svg>
"""


if __name__ == "__main__":
    if "--import" in sys.argv:
        import_sprites(Path(sys.argv[sys.argv.index("--import") + 1]))
    if "--voice" in sys.argv:
        voice()
    timing = json.loads((TK / "timing.json").read_text())
    if [x["line"] for x in timing] != LINES:
        sys.exit("LINES changed since the last --voice run: rerun with --voice")
    OUT.mkdir(exist_ok=True)
    for name in THEMES:
        svg = build(name, timing)
        path = OUT / f"talker-{name}.svg"
        path.write_text(svg, encoding="utf-8")
        print(f"{path.relative_to(ROOT)}  {len(svg) / 1024:.1f} KB")
