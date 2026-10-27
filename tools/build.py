#!/usr/bin/env python3
"""Build the artwork for the Y1tong GitHub profile README.

README images can't load web fonts, so every piece of text is converted to
glyph outlines with fontTools and the SVGs look the same on every machine.
Each image is written once per theme; README.md picks one with <picture>.

    python tools/build.py          # writes assets/*.svg and preview.html

Fonts live in tools/fonts: Manrope, Instrument Serif and Fira Mono (OFL), plus
subsets of FandolSong / FandolHei (GPL + font exception) that cover only the
Chinese characters used here. A full TeX Live copy is preferred when present.
"""

from __future__ import annotations

import html
import math
import random
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONTS = ROOT / "tools" / "fonts"
TEXLIVE = Path("D:/texlive/2025/texmf-dist/fonts/opentype/public")


# ── themes ────────────────────────────────────────────────────────────────
# Dark follows the portfolio (zgh.netlify.app): near-black space, a lit limb.
# Light is the same drawing on graph paper.

DARK = dict(
    name="dark", bg="#06080c", bg2="#0c1322", panel="#090c11", art="#07090e", chip="#0d1219",
    border="#1b2230", grid="#111823", ink="#eef2f8", ink2="#c3ccd9", muted="#7f8a9c",
    faint="#475264", line="#262f3e", accent="#7aa2ff", limb="#b8d0ff", glow="#3d6dff",
    ok="#8fffad", star="#dbe6ff", planet=("#04060a", "#060a12", "#0b1629", "#1a3a6b"),
    ielts="#8fffad", orbit="#8ea4ff", veil="#ff8d70", jnu="#ffe74c", mongolia="#c299ff",
    intern="#7af2ff",
)
LIGHT = dict(
    name="light", bg="#f7f6f2", bg2="#eef0f6", panel="#fbfaf7", art="#f2f0ea", chip="#ffffff",
    border="#e1ddd3", grid="#e9e5dc", ink="#0e152e", ink2="#2b3450", muted="#5e687d",
    faint="#a2aaba", line="#d3d8e1", accent="#2f5bff", limb="#2f5bff", glow="#8aa5ff",
    ok="#13a157", star="#8d97ab", planet=("#f7f6f2", "#eef1f7", "#e0e7f5", "#c7d5f3"),
    ielts="#0c9a6a", orbit="#3a53e0", veil="#e0532f", jnu="#b07d00", mongolia="#7b4fe0",
    intern="#0b8fb0",
)


# ── fonts and text ────────────────────────────────────────────────────────

def num(v: float, nd: int = 2) -> str:
    s = f"{v:.{nd}f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def _kerning(tt: TTFont):
    """Pair kerning from the GPOS 'kern' feature: explicit pairs + class subtables."""
    pairs, classes = {}, []
    if "GPOS" not in tt or not tt["GPOS"].table.FeatureList:
        return pairs, classes
    table = tt["GPOS"].table
    lookups = sorted({i for rec in table.FeatureList.FeatureRecord if rec.FeatureTag == "kern"
                      for i in rec.Feature.LookupListIndex})

    def xadv(v):
        return (getattr(v, "XAdvance", 0) or 0) if v is not None else 0

    for i in lookups:
        lookup = table.LookupList.Lookup[i]
        for sub in lookup.SubTable:
            if lookup.LookupType == 9:
                if sub.ExtensionLookupType != 2:
                    continue
                sub = sub.ExtSubTable
            elif lookup.LookupType != 2:
                continue
            if sub.Format == 1:
                for first, pairset in zip(sub.Coverage.glyphs, sub.PairSet):
                    for rec in pairset.PairValueRecord:
                        pairs.setdefault((first, rec.SecondGlyph), xadv(rec.Value1))
            elif sub.Format == 2:
                values = [[xadv(c2.Value1) for c2 in c1.Class2Record] for c1 in sub.Class1Record]
                classes.append((set(sub.Coverage.glyphs),
                                getattr(sub.ClassDef1, "classDefs", {}),
                                getattr(sub.ClassDef2, "classDefs", {}), values))
    return pairs, classes


class Font:
    """One face (variable fonts are pinned to a single weight) and its kerning."""

    def __init__(self, key: str, path: Path, wght: float | None = None):
        tt = TTFont(path)
        if wght is not None:
            tt = instancer.instantiateVariableFont(tt, {"wght": wght})
        self.key = key
        self.upm = tt["head"].unitsPerEm
        self.cmap = tt.getBestCmap()
        self.glyphs = tt.getGlyphSet()
        self.adv = {g: m[0] for g, m in tt["hmtx"].metrics.items()}
        self.pairs, self.classes = _kerning(tt)

    def has(self, ch: str) -> bool:
        return ord(ch) in self.cmap

    def kern(self, a: str, b: str) -> int:
        if (a, b) in self.pairs:
            return self.pairs[(a, b)]
        for cover, cls1, cls2, values in self.classes:
            if a in cover:
                return values[cls1.get(a, 0)][cls2.get(b, 0)]
        return 0


def font_file(name: str, texlive_dir: str) -> Path:
    for p in (TEXLIVE / texlive_dir / name, FONTS / name):
        if p.exists():
            return p
    raise SystemExit(f"missing font {name}; put a copy in {FONTS}")


def layout(stack, s, size, track=0.0):
    """Place each character with the first font in `stack` that has it.
    `track` is extra letter spacing in em. Returns ([(font, glyph, x)], width)."""
    placed, x, prev = [], 0.0, None
    for i, ch in enumerate(s):
        font = next((f for f in stack if f.has(ch)), None)
        if font is None:
            raise SystemExit(f"no font in the stack has {ch!r} (U+{ord(ch):04X})")
        name = font.cmap[ord(ch)]
        if prev and prev[0] is font:
            x += font.kern(prev[1], name) * size / font.upm
        placed.append((font, name, x))
        x += font.adv.get(name, 0) * size / font.upm
        if i < len(s) - 1:
            x += track * size
        prev = (font, name)
    return placed, x


def measure(stack, s, size, track=0.0):
    return layout(stack, s, size, track)[1]


def wrap(stack, s, size, width, track=0.0):
    lines, cur = [], ""
    for word in s.split(" "):
        trial = f"{cur} {word}".strip()
        if cur and measure(stack, trial, size, track) > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur] if cur else lines


class Doc:
    """An SVG under construction. Glyph outlines are defined once and <use>d."""

    def __init__(self, w, h, label, pad=(0, 0, 0, 0)):
        self.w, self.h, self.label = w, h, label
        self.pad = pad   # transparent margin (left, top, right, bottom), e.g. a grid gutter
        self.defs, self.body = [], []
        self._glyphs, self._glyph_defs, self._n = {}, [], 0

    def uid(self, prefix="u"):
        self._n += 1
        return f"{prefix}{self._n}"

    def add(self, *parts):
        self.body.extend(parts)

    def define(self, *parts):
        self.defs.extend(parts)

    def _glyph(self, font, name):
        key = (font.key, name)
        if key not in self._glyphs:
            pen = SVGPathPen(font.glyphs, ntos=lambda v: num(v, 1))
            font.glyphs[name].draw(TransformPen(pen, (1, 0, 0, -1, 0, 0)))
            d = pen.getCommands()
            gid = f"g{len(self._glyph_defs)}" if d else None
            self._glyphs[key] = gid
            if gid:
                self._glyph_defs.append(f'<path id="{gid}" d="{d}"/>')
        return self._glyphs[key]

    def text(self, stack, s, size, x, y, fill, track=0.0, anchor="start", opacity=None):
        placed, w = layout(stack, s, size, track)
        x0 = x - {"start": 0, "middle": w / 2, "end": w}[anchor]
        runs = []
        for font, name, gx in placed:
            if not runs or runs[-1][0] is not font:
                runs.append((font, gx, []))
            runs[-1][2].append((name, gx))
        out = []
        for font, rx, items in runs:
            sc = size / font.upm
            uses = "".join(f'<use xlink:href="#{gid}" x="{num((gx - rx) / sc, 1)}"/>'
                           for name, gx in items if (gid := self._glyph(font, name)))
            if uses:
                out.append(f'<g transform="translate({num(x0 + rx)} {num(y)}) scale({num(sc, 6)})">{uses}</g>')
        op = f' opacity="{opacity}"' if opacity is not None else ""
        return f'<g fill="{fill}"{op}>{"".join(out)}</g>'

    def svg(self):
        label = html.escape(self.label, quote=True)
        l, t, r, b = self.pad
        w, h = self.w + l + r, self.h + t + b
        return ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'width="{num(w)}" height="{num(h)}" viewBox="{-l} {-t} {num(w)} {num(h)}" '
                f'role="img" aria-label="{label}"><title>{label}</title>'
                f'<defs>{"".join(self.defs)}{"".join(self._glyph_defs)}</defs>{"".join(self.body)}</svg>\n')


def text_sub(d, stack, base, sub, size, x, y, fill):
    """`base` with a subscript (v₀, Δv₁): the fonts' own subscript digits are too small."""
    out = d.text(stack, base, size, x, y, fill)
    if sub:
        out += d.text(stack, sub, size * .7, x + measure(stack, base, size) + size * .05, y + size * .3, fill)
    return out


# ── drawing helpers ───────────────────────────────────────────────────────

# Moving parts start hidden and SMIL switches them on, so a renderer that
# doesn't animate shows nothing instead of a dot stuck at the origin.
SHOW = '<set attributeName="opacity" to="1"/>'

def frame(d, fill, rx=16):
    """Background of a card; returns a clip path id for its contents."""
    cid = d.uid("frame")
    d.define(f'<clipPath id="{cid}"><rect width="{d.w}" height="{num(d.h)}" rx="{rx}"/></clipPath>')
    d.add(f'<rect width="{d.w}" height="{num(d.h)}" rx="{rx}" fill="{fill}"/>')
    return cid


def border(d, t, rx=16):
    d.add(f'<rect x=".5" y=".5" width="{d.w - 1}" height="{num(d.h - 1)}" rx="{rx - .5}" '
          f'fill="none" stroke="{t["border"]}"/>')


def grid(d, color, step=22, major=5):
    pid = d.uid("grid")
    size = step * major
    lines = "".join(f'<path d="M{i * step} 0V{size}M0 {i * step}H{size}" stroke="{color}" '
                    f'stroke-width="{1 if i == 0 else .5}"/>' for i in range(major))
    d.define(f'<pattern id="{pid}" width="{size}" height="{size}" patternUnits="userSpaceOnUse">{lines}</pattern>')
    return pid


def gradient(d, x1, y1, x2, y2, stops, user=True):
    gid = d.uid("lg")
    units = ' gradientUnits="userSpaceOnUse"' if user else ""
    s = "".join(f'<stop offset="{o}" stop-color="{c}" stop-opacity="{a}"/>' for o, c, a in stops)
    d.define(f'<linearGradient id="{gid}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"{units}>{s}</linearGradient>')
    return gid


def radial(d, cx, cy, r, stops):
    gid = d.uid("rg")
    s = "".join(f'<stop offset="{o}" stop-color="{c}" stop-opacity="{a}"/>' for o, c, a in stops)
    d.define(f'<radialGradient id="{gid}" cx="{num(cx)}" cy="{num(cy)}" r="{num(r)}" '
             f'gradientUnits="userSpaceOnUse">{s}</radialGradient>')
    return gid


def blur(d, sd):
    fid = d.uid("blur")
    d.define(f'<filter id="{fid}" x="-50%" y="-50%" width="200%" height="200%">'
             f'<feGaussianBlur stdDeviation="{sd}"/></filter>')
    return fid


def path_from(pts):
    return "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts)


def smooth_path(pts):
    """Catmull-Rom spline through pts, as cubic Béziers."""
    d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0, p1, p2 = pts[max(i - 1, 0)], pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}"
    return d


def circle_arc(cx, cy, r, xmax, ymax):
    """Arc of a circle centred below-right of the canvas: from where it crosses
    y = ymax on the left to where it crosses x = xmax on the right."""
    x1 = cx - math.sqrt(r * r - (cy - ymax) ** 2)
    y2 = cy - math.sqrt(r * r - (cx - xmax) ** 2)
    return f"M{x1:.1f} {ymax:.1f}A{r:.1f} {r:.1f} 0 0 1 {xmax:.1f} {y2:.1f}"


def pulse(x, y, color, r=3.2, dur=2.4):
    return (f'<circle cx="{num(x)}" cy="{num(y)}" r="{r}" fill="{color}"/>'
            f'<circle cx="{num(x)}" cy="{num(y)}" r="{r}" fill="none" stroke="{color}" stroke-width="1.2">'
            f'<animate attributeName="r" values="{r};{num(r * 3.4)}" dur="{dur}s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values=".9;0" dur="{dur}s" repeatCount="indefinite"/></circle>')


def corner_marks(d, color, inset=14, size=7):
    W, H, i, s = d.w, d.h, inset, size
    d.add(f'<path d="M{i} {i + s}V{i}H{i + s}M{W - i - s} {i}H{W - i}V{i + s}'
          f'M{W - i} {num(H - i - s)}V{num(H - i)}H{W - i - s}M{i + s} {num(H - i)}H{i}V{num(H - i - s)}" '
          f'fill="none" stroke="{color}" stroke-width=".9"/>')


# ── shuttlecock physics (footer and the JNU Badminton card) ──────────────

def flight(v0, deg, h0=2.3, vt=6.8, g=9.81, dt=0.002):
    """A shuttlecock under gravity and quadratic drag (terminal speed vt), until
    it falls back through the hitting height h0. Returns [(t, x, y, vx, vy)]."""
    k = g / vt ** 2
    a = math.radians(deg)
    x, y, vx, vy, t = 0.0, h0, v0 * math.cos(a), v0 * math.sin(a), 0.0
    out = [(t, x, y, vx, vy)]
    while not (vy < 0 and y <= h0):
        v = math.hypot(vx, vy)
        vx -= k * v * vx * dt
        vy -= (g + k * v * vy) * dt
        x += vx * dt
        y += vy * dt
        t += dt
        out.append((t, x, y, vx, vy))
    return out


def clear_shot(span=11.4, deg=30):
    """The launch speed for a clear that carries `span` metres between hits."""
    lo, hi = 5.0, 200.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if flight(mid, deg)[-1][1] < span else (lo, mid)
    path = flight(hi, deg)
    return hi, path[::10] + ([path[-1]] if (len(path) - 1) % 10 else [])


def shuttle_def(d):
    sid = d.uid("shuttle")
    d.define(f'<g id="{sid}"><path d="M-1.6 -2.1L-12 -5.4M-1.6 2.1L-12 5.4M-12 -5.4Q-13.4 0 -12 5.4'
             f'M-1.6 -.8L-12 -1.9M-1.6 .8L-12 1.9" fill="none" stroke-width=".9" stroke-linecap="round"/>'
             f'<circle r="2.5" stroke="none"/></g>')
    return sid


def motion_keys(times, pts):
    """keyTimes / keyPoints for <animateMotion> so speed along a polyline matches
    the timestamps of its points."""
    s = [0.0]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        s.append(s[-1] + math.hypot(x2 - x1, y2 - y1))
    T, L = times[-1], s[-1]
    kt = ";".join(num(v / T, 4) for v in times)
    kp = ";".join(num(v / L, 4) for v in s)
    return kt, kp


# ── header ────────────────────────────────────────────────────────────────

PHRASES = [
    "Turning complexity into clarity.",
    "A designer who starts from math.",
    "Searching for the global optimum.",
    "Building an AI speaking coach.",
    "Badminton club president, too.",
]


def typing(d, stack, phrases, size, x, y, color, caret, slot=4.0):
    """Phrases typed and erased in turn: each is revealed by an animated clip,
    and one caret follows whichever is active. Without SMIL the first phrase
    simply stands there."""
    total = slot * len(phrases)
    first = measure(stack, phrases[0], size)
    out, ct, cv = [], [], []
    for i, p in enumerate(phrases):
        w = measure(stack, p, size)
        s = i * slot
        marks = [(s, 0.0), (s + 1.15, w), (s + 3.2, w), (s + 3.6, 0.0)]
        times = ([0.0] if i else []) + [m[0] for m in marks] + [total]
        vals = ([0.0] if i else []) + [m[1] for m in marks] + [0.0]
        cid = d.uid("type")
        static = num(w + 8, 1) if i == 0 else 0
        d.define(f'<clipPath id="{cid}"><rect x="{x - 4}" y="{y - size}" height="{size * 1.5}" width="{static}">'
                 f'<animate attributeName="width" values="{";".join(num(v + 8 if v else 0, 1) for v in vals)}" '
                 f'keyTimes="{";".join(num(v / total, 4) for v in times)}" dur="{total}s" '
                 f'repeatCount="indefinite"/></rect></clipPath>')
        out.append(f'<g clip-path="url(#{cid})">{d.text(stack, p, size, x, y, color)}</g>')
        ct += [m[0] for m in marks]
        cv += [x + m[1] + 4 for m in marks]
    ct.append(total)
    cv.append(x + 4)
    out.append(f'<rect x="{num(x + first + 4, 1)}" y="{num(y - size * .76)}" width="1.6" height="{num(size * .96)}" fill="{caret}">'
               f'<animate attributeName="x" values="{";".join(num(v, 1) for v in cv)}" '
               f'keyTimes="{";".join(num(v / total, 4) for v in ct)}" dur="{total}s" repeatCount="indefinite"/>'
               f'<animate attributeName="opacity" values="1;0" calcMode="discrete" dur="1.1s" '
               f'repeatCount="indefinite"/></rect>')
    return "".join(out)


def header(t):
    W, H = 880, 320
    dark = t["name"] == "dark"
    d = Doc(W, H, "Zhang Guohao 张国皓 — Mathematics · Visual Design · Data Systems. "
                  "Turning complexity into clarity.")
    clip = frame(d, t["bg"], rx=18)
    out = [f'<g clip-path="url(#{clip})">']

    sky = radial(d, 820, 30, 820, [(0, t["bg2"], 1), (1, t["bg"], 1)])
    out.append(f'<rect width="{W}" height="{H}" fill="url(#{sky})"/>')
    if not dark:
        out.append(f'<rect width="{W}" height="{H}" fill="url(#{grid(d, t["grid"])})"/>')

    # the planet: its limb sweeps from the bottom edge up to the top-right corner
    CX, CY, R = 1135.2, 804.0, 782.8
    text_boxes = [(50, 44, 400, 66), (50, 76, 210, 110), (50, 106, 480, 158), (50, 166, 480, 190),
                  (50, 208, 480, 254), (50, 274, 450, 298)]
    rnd = random.Random(11)
    for _ in range(180 if dark else 34):
        x, y = rnd.uniform(6, W - 6), rnd.uniform(6, H - 6)
        if math.hypot(x - CX, y - CY) < R + 4:
            continue
        if any(x1 <= x <= x2 and y1 <= y <= y2 for x1, y1, x2, y2 in text_boxes):
            continue
        if dark:
            r, o = rnd.uniform(.3, 1.05), rnd.uniform(.18, .85)
            tw = ""
            if rnd.random() < .14:
                tw = (f'<animate attributeName="opacity" values="{o:.2f};1;{o:.2f}" '
                      f'dur="{rnd.uniform(2.4, 5):.1f}s" begin="-{rnd.uniform(0, 5):.1f}s" repeatCount="indefinite"/>')
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="{t["star"]}" opacity="{o:.2f}">{tw}</circle>')
        else:
            out.append(f'<path d="M{x - 2.5:.1f} {y:.1f}h5M{x:.1f} {y - 2.5:.1f}v5" stroke="{t["star"]}" '
                       f'stroke-width=".8" opacity=".6"/>')

    p0, p1, p2, p3 = t["planet"]
    fill = radial(d, CX, CY, R, [(0, p0, 1), (.84, p1, 1), (.962, p2, 1), (1, p3, 1)])
    limb = gradient(d, 470, 330, 900, 30, [(0, t["limb"], .04), (.5, t["limb"], .5), (1, t["limb"], 1)])
    haze = gradient(d, 470, 330, 900, 30, [(0, t["glow"], 0), (.55, t["glow"], .35), (1, t["glow"], .9)])
    arc = circle_arc(CX, CY, R, W + 40, H + 40)
    out.append(f'<path d="{arc}" fill="none" stroke="url(#{haze})" stroke-width="46" '
               f'opacity="{.55 if dark else .4}" filter="url(#{blur(d, 14)})"/>')
    out.append(f'<circle cx="{CX}" cy="{CY}" r="{R}" fill="url(#{fill})"/>')
    for i in range(1, 8):   # faint level sets under the limb
        out.append(f'<path d="{circle_arc(CX, CY, R - i * 15, W + 40, H + 40)}" fill="none" '
                   f'stroke="{t["limb"]}" stroke-opacity="{.09 - i * .0095:.3f}" stroke-width=".8"/>')
    out.append(f'<path d="{arc}" fill="none" stroke="url(#{haze})" stroke-width="6" filter="url(#{blur(d, 4)})"/>')
    out.append(f'<path d="{arc}" fill="none" stroke="url(#{limb})" stroke-width="1.4"/>')

    # two orbits and a low-thrust transfer between them
    def polar(r, a):
        return CX + r * math.cos(a), CY + r * math.sin(a)

    rad = math.radians
    R1, R2 = R + 40, R + 112
    ta, tb = rad(-141), rad(-122)
    out.append(f'<path d="{circle_arc(CX, CY, R1, W + 40, H + 40)}" fill="none" stroke="{t["muted"]}" '
               f'stroke-width="1.2" stroke-dasharray="0 6" stroke-linecap="round" opacity=".8"/>')
    outer = [polar(R2, tb + (rad(-84) - tb) * i / 40) for i in range(41)]
    out.append(f'<path d="{path_from(outer)}" fill="none" stroke="{t["muted"]}" stroke-width="1.2" '
               f'stroke-dasharray="0 6" stroke-linecap="round" opacity=".8"/>')
    transfer = [polar(R1 + (R2 - R1) * (u * u * (3 - 2 * u)), ta + (tb - ta) * u)
                for u in (i / 60 for i in range(61))]
    out.append(f'<path d="{path_from(transfer)}" fill="none" stroke="{t["accent"]}" stroke-width="1.3"/>')

    trail = gradient(d, 0, 0, 1, 0, [(0, t["accent"], 0), (1, t["accent"], .9)], user=False)
    route = ([polar(R1, rad(-152) + (ta - rad(-152)) * i / 50) for i in range(50)] + transfer
             + [polar(R2, tb + (rad(-84) - tb) * i / 40) for i in range(1, 41)])
    ring = [polar(R1, rad(-150) + rad(52) * i / 80) for i in range(81)]
    for path, dur, begin in ((path_from(route), 16, -3), (path_from(ring), 23, -15)):
        out.append(f'<g opacity="0"><rect x="-26" y="-.75" width="26" height="1.5" rx=".75" fill="url(#{trail})"/>'
                   f'<circle r="6" fill="{t["accent"]}" opacity=".22"/><circle r="1.9" fill="{t["ink"]}"/>'
                   f'<animateMotion dur="{dur}s" begin="{begin}s" repeatCount="indefinite" rotate="auto" '
                   f'path="{path}"/>{SHOW}</g>')
    for a, r, sub, dx, dy in ((ta, R1, "1", 9, 15), (tb, R2, "2", -30, -7)):
        x, y = polar(r, a)
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.8" fill="{t["bg"]}" stroke="{t["accent"]}" stroke-width="1.2"/>')
        out.append(text_sub(d, MONO, "Δv", sub, 10, x + dx, y + dy, t["accent"]))
    out.append(d.text(MONO, "r(θ) = a(1 − e²) / (1 + e·cos θ)", 9.5, W - 30, H - 28, t["muted"], anchor="end"))

    # type
    x0 = 56
    out.append(f'<rect x="{x0}" y="52" width="6" height="6" fill="{t["accent"]}"/>')
    out.append(d.text(MONO, "PROFILE / 2026  ·  23.13°N 113.35°E", 10, x0 + 16, 58.5, t["muted"], track=.14))
    out.append(d.text(CJK_SERIF, "张国皓", 21, x0, 102, t["ink2"], track=.34))
    name_w = measure(SANS7, "ZHANG GUOHAO", 44, .1)
    out.append(d.text(SANS7, "ZHANG GUOHAO", 44, x0 - 2, 150, t["ink"], track=.1))
    sub = "MATHEMATICS · VISUAL DESIGN · DATA SYSTEMS"
    track = (name_w - measure(SANS6, sub, 11)) / ((len(sub) - 1) * 11)   # justify to the name
    out.append(d.text(SANS6, sub, 11, x0, 182, t["ink2"], track=track, opacity=.85))
    out.append(typing(d, SERIF, PHRASES, 30, x0, 240, t["ink"], t["accent"]))
    out.append(pulse(x0 + 4, 286.5, t["ok"]))
    out.append(d.text(MONO, "AVAILABLE FOR INTERNSHIPS  ·  GUANGZHOU / SHENZHEN", 9.5, x0 + 18, 290,
                      t["muted"], track=.14))
    out.append("</g>")
    d.add(*out)
    corner_marks(d, t["faint"])
    border(d, t, rx=18)
    return d.svg()


# ── project cards ─────────────────────────────────────────────────────────

def art_panel(d, t, x, y, w, h, rx=10):
    cid = d.uid("art")
    d.define(f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/></clipPath>')
    return cid, (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{t["art"]}"/>'
                 f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#{grid(d, t["grid"], 16)})" '
                 f'clip-path="url(#{cid})"/>')


def art_ielts(d, t, w, h, c):
    rnd = random.Random(3)
    out = [d.text(MONO, "PART 1 · QUESTION 2/3", 9, 18, 28, t["muted"], track=.12),
           f'<circle cx="{w - 52}" cy="24.8" r="3" fill="{c}"><animate attributeName="opacity" '
           f'values="1;.15;1" dur="1.6s" repeatCount="indefinite"/></circle>',
           d.text(MONO, "REC", 9, w - 44, 28, t["muted"], track=.12),
           d.text(SERIF, "“Do you prefer mornings or evenings?”", 18, 18, 58, t["ink"])]
    # the answer as a waveform; a playhead sweeps it and colours what it has heard
    n, x1, x2, mid = 64, 20, w - 20, 104
    step = (x2 - x1) / (n - 1)
    bars = "".join(
        f"M{x1 + i * step:.1f} {mid - hh:.1f}V{mid + hh:.1f}"
        for i in range(n)
        for hh in [2.5 + 26 * ((math.sin(i * .23) ** 2) * .72 + .28 * math.sin(i * .061 + .9) ** 2)
                   * rnd.uniform(.4, 1)])
    out.append(f'<path d="{bars}" stroke="{t["faint"]}" stroke-width="2.4" stroke-linecap="round" opacity=".6"/>')
    rec = d.uid("rec")
    d.define(f'<clipPath id="{rec}"><rect x="{x1 - 3}" y="{mid - 34}" height="68" width="{x2 - x1 + 6}">'
             f'<animate attributeName="width" values="0;{x2 - x1 + 6};{x2 - x1 + 6}" keyTimes="0;.85;1" '
             f'dur="7s" repeatCount="indefinite"/></rect></clipPath>')
    out.append(f'<path d="{bars}" stroke="{c}" stroke-width="2.4" stroke-linecap="round" clip-path="url(#{rec})"/>')
    out.append(f'<path d="M0 {mid - 32}V{mid + 32}" transform="translate({x2} 0)" stroke="{t["ink"]}" '
               f'stroke-width="1" opacity=".7">'
               f'<animateTransform attributeName="transform" type="translate" values="{x1} 0;{x2} 0;{x2} 0" '
               f'keyTimes="0;.85;1" dur="7s" repeatCount="indefinite"/></path>')
    # the transcript, with the three changes that matter most
    marks = {(0, 2): "1", (1, 3): "2", (2, 1): "3"}
    for row, y in enumerate((152, 172, 192)):
        x, col = 20.0, 0
        limit = x2 if row < 2 else x1 + (x2 - x1) * .62
        while True:
            ww = rnd.uniform(18, 58)
            if x + ww > limit:
                break
            m = marks.get((row, col))
            if m:
                out.append(f'<rect x="{x - 3:.1f}" y="{y - 6}" width="{ww + 6:.1f}" height="12" rx="6" '
                           f'fill="{c}" fill-opacity=".16" stroke="{c}"/>')
                out.append(f'<circle cx="{x + ww + 6:.1f}" cy="{y - 7}" r="6.5" fill="{c}"/>')
                out.append(d.text(MONO, m, 8.5, x + ww + 6, y - 4, t["art"], anchor="middle"))
                x += 10
            else:
                out.append(f'<rect x="{x:.1f}" y="{y - 3}" width="{ww:.1f}" height="6" rx="3" fill="{t["faint"]}" opacity=".55"/>')
            x += ww + 7
            col += 1
    out.append(d.text(MONO, "TRANSCRIPT  →  THE 3 CHANGES THAT MATTER MOST", 8.5, 20, h - 16, t["muted"], track=.12))
    return "".join(out)


def art_orbital(d, t, w, h, c):
    out = []
    pcx, pcy, pr = 96, 262, 168
    p0, p1, p2, p3 = t["planet"]
    fill = radial(d, pcx, pcy, pr, [(0, p0, 1), (.8, p1, 1), (.95, p2, 1), (1, p3, 1)])
    out.append(f'<circle cx="{pcx}" cy="{pcy}" r="{pr}" fill="url(#{fill})" stroke="{c}" stroke-width="1.2"/>')
    top, ty = pcy - pr, 18
    dest = (w - 52, 40)
    # space elevator, rocket, and the hybrid: elevator to the top, rocket onwards
    rocket = f"M180 116.5Q250 26 {dest[0] - 13} {dest[1] + 5}"
    hybrid = f"M{pcx + 8} {ty}Q220 -6 {dest[0] - 14} {dest[1] - 4}"
    out.append(f'<path d="M{pcx} {top}V{ty}" stroke="{c}" stroke-width="1.3"/>')
    out.append(f'<rect x="{pcx - 8}" y="{ty - 6}" width="16" height="7" rx="1.5" fill="{t["art"]}" stroke="{c}"/>')
    out.append(f'<rect x="{pcx - 3}" y="{(top + ty) / 2:.0f}" width="6" height="4" rx="1" fill="{t["ink"]}">'
               f'<animate attributeName="y" values="{top - 6};{ty + 3};{top - 6}" dur="9s" repeatCount="indefinite"/></rect>')
    for p in (rocket, hybrid):
        out.append(f'<path d="{p}" fill="none" stroke="{c}" stroke-width="1.1" stroke-dasharray="3 4" opacity=".75"/>')
    for p, dur, begin in ((rocket, 5, -1), (hybrid, 6.5, -4)):
        out.append(f'<circle r="2.4" fill="{t["ink"]}" opacity="0"><animateMotion dur="{dur}s" begin="{begin}s" '
                   f'repeatCount="indefinite" path="{p}"/>{SHOW}</circle>')
    out.append(f'<ellipse cx="{dest[0]}" cy="{dest[1]}" rx="24" ry="7.5" fill="none" stroke="{t["muted"]}" '
               f'stroke-dasharray="0 4" stroke-linecap="round"/>')
    out.append(f'<circle cx="{dest[0]}" cy="{dest[1]}" r="9" fill="{t["art"]}" stroke="{t["ink2"]}"/>'
               f'<circle cx="{dest[0]}" cy="{dest[1]}" r="3.2" fill="{t["ink2"]}"/>')
    out.append(f'<g transform="translate({pcx + 15} {top - 6}) rotate(-90)">'
               f'{d.text(MONO, "ELEVATOR", 8, 0, 0, t["muted"], track=.16)}</g>')
    out.append(d.text(MONO, "ROCKET", 8, 238, 92, t["muted"], track=.16))
    out.append(d.text(MONO, "HYBRID", 8, 196, 24, t["muted"], track=.16))
    out.append(d.text(MONO, "TIME · COST · RISK", 8, w - 16, h - 14, t["muted"], track=.16, anchor="end"))
    return "".join(out)


def art_veil(d, t, w, h, c):
    out = []
    ground = h - 18
    out.append(f'<path d="M0 {ground}H{w}" stroke="{t["line"]}"/>')
    tx = 46
    out.append(f'<path d="M{tx - 9} {ground}V{ground - 13}a9 3 0 0 1 18 0V{ground}" fill="{t["art"]}" stroke="{t["ink2"]}"/>'
               f'<ellipse cx="{tx}" cy="{ground - 13}" rx="9" ry="3" fill="none" stroke="{t["ink2"]}"/>')
    M, T = (w + 18, 14), (tx + 6, ground - 10)
    los = f"M{M[0]} {M[1]}L{T[0]} {T[1]}"
    out.append(f'<path d="{los}" stroke="{t["muted"]}" stroke-dasharray="2 4"/>')
    for i, (f, r) in enumerate(((.40, 16), (.51, 19), (.62, 15))):
        cx, cy = M[0] + f * (T[0] - M[0]), M[1] + f * (T[1] - M[1])
        smoke = radial(d, 0, 0, r, [(0, c, .55), (.6, c, .25), (1, c, 0)])
        out.append(f'<g transform="translate({cx:.1f} {cy:.1f})"><circle r="{r}" fill="url(#{smoke})">'
                   f'<animateTransform attributeName="transform" type="translate" values="0 -5;0 7;0 -5" '
                   f'dur="{8 + i}s" begin="-{i * 2.5}s" repeatCount="indefinite"/></circle></g>')
        ux, uy = cx + 34, 22 + i * 8
        out.append(f'<path d="M{ux:.1f} {uy}Q{ux - 14:.1f} {uy + 2} {cx + 3:.1f} {cy - r + 4:.1f}" fill="none" '
                   f'stroke="{c}" stroke-dasharray="2 3" opacity=".8"/>')
        out.append(f'<g transform="translate({ux:.1f} {uy})" stroke="{t["ink2"]}" stroke-width="1" fill="none">'
                   f'<path d="M-5 -2.5L5 2.5M-5 2.5L5 -2.5"/><circle cx="-5.5" cy="-2.8" r="1.8"/>'
                   f'<circle cx="5.5" cy="-2.8" r="1.8"/><circle cx="-5.5" cy="2.8" r="1.8"/>'
                   f'<circle cx="5.5" cy="2.8" r="1.8"/></g>')
    out.append(f'<path d="M3 -2.2L-5 0L3 2.2z" fill="{t["ink"]}" opacity="0">'
               f'<animateMotion dur="6s" repeatCount="indefinite" rotate="auto-reverse" path="{los}"/>{SHOW}</path>')
    out.append(d.text(MONO, "MISSILE", 8, w - 16, 52, t["muted"], track=.16, anchor="end"))
    out.append(d.text(MONO, "UAV × 3", 8, 214, 14, t["muted"], track=.16))
    out.append(d.text(MONO, "TARGET", 8, tx, h - 6, t["muted"], track=.16, anchor="middle"))
    out.append(d.text(MONO, "GA + DE", 8, w - 16, h - 6, t["muted"], track=.16, anchor="end"))
    return "".join(out)


def art_jnu(d, t, w, h, c):
    out = []
    k = 16.5
    L, B = 13.4 * k, 6.1 * k
    x0, y0 = (w - L) / 2, (h - B) / 2
    mx, my = x0 + L / 2, y0 + B / 2
    lines = [f"M{x0:.1f} {y0 + .46 * k:.1f}H{x0 + L:.1f}", f"M{x0:.1f} {y0 + B - .46 * k:.1f}H{x0 + L:.1f}"]
    for xx in (x0 + .76 * k, x0 + L - .76 * k, mx - 1.98 * k, mx + 1.98 * k):
        lines.append(f"M{xx:.1f} {y0:.1f}V{y0 + B:.1f}")
    lines += [f"M{x0:.1f} {my:.1f}H{mx - 1.98 * k:.1f}", f"M{mx + 1.98 * k:.1f} {my:.1f}H{x0 + L:.1f}"]
    out.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{L:.1f}" height="{B:.1f}" fill="none" stroke="{c}" '
               f'stroke-width="1.1" opacity=".85"/>')
    out.append(f'<path d="{"".join(lines)}" stroke="{c}" stroke-width=".9" opacity=".7"/>')
    out.append(f'<path d="M{mx:.1f} {y0 - 5:.1f}V{y0 + B + 5:.1f}" stroke="{t["ink2"]}" stroke-width="2"/>')
    # a clear, side-on, laid over the court like a multiple exposure
    _, path = clear_shot()
    apex = max(p[2] for p in path)
    sx = (L - 1.8 * k) / path[-1][1]
    pts = [(x0 + .9 * k + p[1] * sx, (y0 + B * .7) - (p[2] - 2.3) / (apex - 2.3) * (B * .7 - 6)) for p in path]
    out.append(f'<path d="{path_from(pts)}" fill="none" stroke="{t["ink2"]}" stroke-width=".9" '
               f'stroke-dasharray="2 3" opacity=".7"/>')
    sid = shuttle_def(d)
    for i in range(0, len(path) - 1, 9):
        p, (x, y) = path[i], pts[i]
        ang = math.degrees(math.atan2(-p[4] / (apex - 2.3) * (B * .7 - 6), p[3] * sx))
        out.append(f'<use xlink:href="#{sid}" transform="translate({x:.1f} {y:.1f}) rotate({ang:.0f}) scale(.8)" '
                   f'fill="{t["ink2"]}" stroke="{t["ink2"]}" opacity="{.15 + .35 * i / len(path):.2f}"/>')
    kt, kp = motion_keys([p[0] for p in path], pts)
    out.append(f'<g fill="{t["ink"]}" stroke="{t["ink"]}" opacity="0"><use xlink:href="#{sid}"/>'
               f'<animateMotion dur="{path[-1][0] * 2:.2f}s" repeatCount="indefinite" rotate="auto" '
               f'calcMode="linear" keyTimes="{kt}" keyPoints="{kp}" path="{path_from(pts)}"/>{SHOW}</g>')
    out.append(d.text(MONO, "COURT GRID", 7.5, 12, 18, t["muted"], track=.16))
    out.append(d.text(MONO, "FLIGHT PATH", 7.5, w - 12, 18, t["muted"], track=.16, anchor="end"))
    out.append(d.text(MONO, "13.4 × 6.1 M", 7.5, 12, h - 10, t["muted"], track=.16))
    out.append(d.text(MONO, "1/2000 S", 7.5, w - 12, h - 10, t["muted"], track=.16, anchor="end"))
    return "".join(out)


def art_mongolia(d, t, w, h, c):
    out = []
    for i in range(5):   # rolling grassland, as contour lines
        pts = [(x, 30 + i * 22 + 5 * math.sin(x * .021 + i * 1.7) + 3 * math.sin(x * .053 + i))
               for x in range(-10, w + 20, 12)]
        out.append(f'<path d="{smooth_path(pts)}" fill="none" stroke="{t["faint"]}" stroke-width=".7" opacity=".55"/>')
    stops = [(24, 106), (64, 82), (104, 96), (146, 64), (188, 78), (232, 48), (276, 64), (322, 38), (372, 50)]
    route = smooth_path(stops)
    out.append(f'<path d="{route}" fill="none" stroke="{c}" stroke-width="6" opacity=".14" stroke-linecap="round"/>')
    out.append(f'<path d="{route}" fill="none" stroke="{c}" stroke-width="1.6"/>')
    for i, (x, y) in enumerate(stops):
        if i == 0:
            out.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{t["art"]}" stroke="{c}" stroke-width="1.4"/>')
            continue
        out.append(f'<circle cx="{x}" cy="{y}" r="2.4" fill="{t["art"]}" stroke="{c}" stroke-width="1.2"/>')
        out.append(d.text(MONO, f"D{i}", 7.5, x, y - 8, t["muted"], anchor="middle"))
    out.append(f'<g opacity="0"><circle r="5.5" fill="{c}" opacity=".25"/><circle r="2.4" fill="{t["ink"]}"/>'
               f'<animateMotion dur="11s" repeatCount="indefinite" path="{route}"/>{SHOW}</g>')
    out.append(f'<path d="M22 13l4 9h-8z" fill="{t["ink2"]}"/>')
    out.append(d.text(MONO, "N", 7.5, 22, 32, t["muted"], anchor="middle"))
    out.append(d.text(SANS7, "3,234 KM", 17, w - 16, h - 28, t["ink"], track=.04, anchor="end"))
    out.append(d.text(MONO, "8 DAYS · SELF-DRIVE", 7.5, w - 16, h - 13, t["muted"], track=.16, anchor="end"))
    return "".join(out)


def tag_row(d, t, items, x, y, gap=6, size=9.5):
    out = []
    for item in items:
        tw = measure(MONO, item, size, .06)
        out.append(f'<rect x="{x + .5:.1f}" y="{y + .5}" width="{tw + 17:.1f}" height="21" rx="10.5" '
                   f'fill="{t["chip"]}" stroke="{t["line"]}"/>')
        out.append(d.text(MONO, item, size, x + 9, y + 14.3, t["ink2"], track=.06))
        x += tw + 18 + gap
    return "".join(out)


def flagship(t):
    W, H = 880, 272
    c = t["ielts"]
    d = Doc(W, H, "ieltsspeak (思说口语) — an AI speaking coach for IELTS learners. Listen, answer out loud, "
                  "get a transcript and the three changes that matter most. Open source, MIT.")
    clip = frame(d, t["panel"])
    aid, panel = art_panel(d, t, 456, 12, 412, 248)
    out = [f'<g clip-path="url(#{clip})">', panel,
           f'<g clip-path="url(#{aid})"><g transform="translate(456 12)">{art_ielts(d, t, 412, 248, c)}</g></g>']
    x0 = 32
    out.append(d.text(MONO, "01", 9.5, x0, 46, c, track=.18))
    out.append(d.text(MONO, "/  PRODUCT · 2026", 9.5, x0 + 20, 46, t["muted"], track=.18))
    out.append(d.text(MONO, "OPEN SOURCE · MIT", 9.5, 428, 46, t["muted"], track=.18, anchor="end"))
    out.append(d.text(SANS7, "IELTSSPEAK", 30, x0 - 1, 94, t["ink"], track=.06))
    out.append(d.text(CJK_SANS, "思说口语", 17, x0 + measure(SANS7, "IELTSSPEAK", 30, .06) + 14, 93, t["muted"], track=.12))
    out.append(d.text(SERIF, "An AI speaking coach for IELTS learners.", 20, x0, 124, t["ink2"]))
    body = ("Hear the question, answer out loud, then get a transcript and the three changes that "
            "matter most. The lite edition runs on Node + SQLite or Cloudflare Workers from one codebase.")
    for i, line in enumerate(wrap(SANS4, body, 13, 396)):
        out.append(d.text(SANS4, line, 13, x0, 154 + i * 20, t["muted"]))
    out.append(f'<circle cx="{x0 + 3}" cy="217" r="3" fill="{c}"/>')
    out.append(d.text(SANS6, "Live at ieltsspeak.cn  ·  lite edition on GitHub", 11.5, x0 + 13, 221, t["ink"]))
    out.append(tag_row(d, t, ["TypeScript", "React 19", "vinext", "Cloudflare Workers", "SQLite"], x0, 234))
    out.append("</g>")
    d.add(*out)
    border(d, t)
    return d.svg()


CARDS = [
    dict(slug="orbital-index", accent="orbit", num="02", meta="MCM/ICM 2026", role="TEAM CAPTAIN",
         title="ORBITAL INDEX", subtitle="Space logistics & orbital resource allocation",
         body="Space elevator, rockets, or a hybrid? A multi-objective MILP that trades time, cost and risk, "
              "told as one clear visual story.",
         award="Successful Participant", tags="MILP · MATLAB", art=art_orbital),
    dict(slug="veil-path", accent="veil", num="03", meta="CUMCM 2025", role="TEAM CAPTAIN",
         title="VEIL PATH", subtitle="Multi-UAV smoke-screen deployment",
         body="When and where should each drone release its smoke? A hybrid GA + DE search turns an "
              "invisible decision into explainable paths.",
         award="Guangdong Provincial 2nd Prize", tags="GA · DE", art=art_veil),
    dict(slug="jnu-badminton", accent="jnu", num="04", meta="BRAND IDENTITY", role="EVENT SYSTEM",
         title="JNU BADMINTON", subtitle="A visual system for the club I run",
         body="Court grid, flight paths and high-speed photography as one identity system, for a club "
              "of 100+ members and 30+ events a term.",
         award="Club president since 2025", tags="IDENTITY · PHOTO", art=art_jnu),
    dict(slug="inner-mongolia", accent="mongolia", num="05", meta="ROUTE DESIGN · FILM", role="8 DAYS",
         title="INNER MONGOLIA", subtitle="3,234 km, told as one visual story",
         body="An eight-day self-drive: route planning, map design, field photography and a vlog, "
              "organised into a single travel narrative.",
         award="Personal project", tags="MAP · PHOTO · FILM", art=art_mongolia),
]


def grid_card(t, spec, column):
    """A half-width card. README places two per row at 50% each with no space
    between them, so the 10px gutter is drawn into the cards themselves."""
    W, H = 430, 306
    c = t[spec["accent"]]
    pad = (0, 0, 5, 5) if column == 0 else (5, 0, 0, 5)
    d = Doc(W, H, f'{spec["title"]} — {spec["subtitle"]}. {spec["body"]} {spec["award"]}.', pad)
    clip = frame(d, t["panel"])
    aid, panel = art_panel(d, t, 12, 12, W - 24, 132)
    out = [f'<g clip-path="url(#{clip})">', panel,
           f'<g clip-path="url(#{aid})"><g transform="translate(12 12)">{spec["art"](d, t, W - 24, 132, c)}</g></g>']
    x0 = 24
    out.append(d.text(MONO, spec["num"], 9, x0, 172, c, track=.18))
    out.append(d.text(MONO, f'/  {spec["meta"]}', 9, x0 + 19, 172, t["muted"], track=.18))
    out.append(d.text(MONO, spec["role"], 9, W - x0, 172, t["muted"], track=.18, anchor="end"))
    out.append(d.text(SANS7, spec["title"], 21, x0 - 1, 203, t["ink"], track=.07))
    out.append(d.text(SERIF, spec["subtitle"], 16.5, x0, 227, t["ink2"]))
    lines = wrap(SANS4, spec["body"], 12, W - 2 * x0)
    assert len(lines) <= 2, (spec["slug"], lines)
    for i, line in enumerate(lines):
        out.append(d.text(SANS4, line, 12, x0, 251 + i * 17, t["muted"]))
    out.append(f'<circle cx="{x0 + 3}" cy="287.5" r="3" fill="{c}"/>')
    out.append(d.text(SANS6, spec["award"], 11.5, x0 + 13, 291.5, t["ink"]))
    out.append(d.text(MONO, spec["tags"], 9, W - x0, 291, t["muted"], track=.14, anchor="end"))
    out.append("</g>")
    d.add(*out)
    border(d, t)
    return d.svg()


# ── toolkit ───────────────────────────────────────────────────────────────

PROJECTS = {"ielts": "ieltsspeak", "orbit": "Orbital Index", "veil": "Veil Path",
            "jnu": "JNU Badminton", "mongolia": "Inner Mongolia", "intern": "Data internship"}

TOOLKIT = [
    ("MATH", [("Probability & Statistics", []), ("Linear Algebra", []), ("Mathematical Analysis", []),
              ("Multivariable Calculus", []), ("Financial Mathematics", [])]),
    ("OPTIMIZE", [("Linear Programming", []), ("Mixed-Integer Programming", ["orbit"]),
                  ("Multi-objective", ["orbit"]), ("Genetic Algorithm", ["veil"]),
                  ("Differential Evolution", ["veil"]), ("Simulated Annealing", [])]),
    ("CODE", [("C", []), ("MATLAB", ["orbit"]), ("Python", ["intern"]), ("R", []),
              ("TypeScript", ["ielts"]), ("React", ["ielts"]), ("LaTeX", [])]),
    ("DATA", [("Pandas", ["intern"]), ("NumPy", ["intern"]), ("Data Cleaning", ["intern"]),
              ("Statistical Modeling", ["intern"]), ("Data Visualization", ["orbit"])]),
    ("DESIGN", [("Visual Systems", ["jnu"]), ("Information Design", ["orbit", "veil", "mongolia"]),
                ("Brand Identity", ["jnu"]), ("Photography", ["jnu", "mongolia"]),
                ("Motion & Film", ["mongolia"])]),
]


def toolkit(t):
    W = 880
    d = Doc(W, 0, "Toolkit — " + "; ".join(f'{g}: {", ".join(i for i, _ in items)}' for g, items in TOOLKIT))
    xl, xc, xr = 30, 166, W - 28
    ch, gap, ggap = 28, 8, 14
    out, y = [], 26.0
    for gi, (group, items) in enumerate(TOOLKIT, 1):
        out.append(d.text(MONO, f"{gi:02d}", 9.5, xl, y + 18, t["accent"], track=.1))
        out.append(d.text(MONO, group, 9.5, xl + 26, y + 18, t["ink2"], track=.22))
        x = xc
        for label, used in items:
            tw = measure(SANS5, label, 12.5)
            cw = tw + 24 + (13 + 9 * len(used) if used else 0)
            if x + cw > xr:
                x, y = xc, y + ch + 8
            out.append(f'<rect x="{x + .5:.1f}" y="{y + .5:.1f}" width="{cw - 1:.1f}" height="{ch - 1}" '
                       f'rx="{(ch - 1) / 2}" fill="{t["chip"]}" stroke="{t["line"]}"/>')
            out.append(d.text(SANS5, label, 12.5, x + 12, y + 18.4, t["ink2"]))
            for j, key in enumerate(used):
                out.append(f'<circle cx="{x + 12 + tw + 13 + 9 * j:.1f}" cy="{y + ch / 2}" r="3.1" fill="{t[key]}"/>')
            x += cw + gap
        y += ch
        if gi < len(TOOLKIT):
            out.append(f'<path d="M{xl} {y + ggap:.1f}H{xr}" stroke="{t["line"]}" stroke-width=".8"/>')
            y += 2 * ggap
    y += 34
    out.append(f'<path d="M{xl} {y - 20:.1f}H{xr}" stroke="{t["line"]}" stroke-width=".8" stroke-dasharray="2 3"/>')
    out.append(d.text(MONO, "PUT TO WORK IN", 9, xl, y + 3.5, t["muted"], track=.18))
    x = xc
    for key, label in PROJECTS.items():
        out.append(f'<circle cx="{x + 3}" cy="{y}" r="3.1" fill="{t[key]}"/>')
        out.append(d.text(SANS5, label, 11, x + 11, y + 3.8, t["ink2"]))
        x += measure(SANS5, label, 11) + 30
    out.append(d.text(SERIF, "No dot: coursework or self-taught.", 13.5, xc, y + 27, t["muted"]))
    d.h = y + 48
    frame(d, t["panel"])
    d.add(*out)
    border(d, t)
    return d.svg()


# ── convergence (the timeline) ────────────────────────────────────────────

GENERATIONS = [
    ("2024.09", "Hello, JNU", "Math & Applied Math; Youth League branch secretary"),
    ("2025.09", "CUMCM 2025", "Guangdong 2nd Prize as team captain; badminton club president"),
    ("2025.11", "National Games", "Volunteer for 55 h; Star of the Week and Service Star"),
    ("2026.02", "MCM/ICM 2026", "Successful Participant as captain; data-analyst internship"),
    ("2025–26", "Red Flag Branch", "May Fourth honour for my branch; Outstanding League Cadre"),
    ("2026.10", "Open source", "ieltsspeak-lite goes public on GitHub. You are here."),
    ("NEXT", "Next iterate", "An internship in Guangzhou or Shenzhen. Your team?"),
]


def convergence(t):
    W = 880
    d = Doc(W, 0, "Convergence — a timeline drawn as an optimizer's best-so-far curve: "
                  + "; ".join(f"{a} {b}: {c}" for a, b, c in GENERATIONS))
    xs = [76 + i * 121.3 for i in range(len(GENERATIONS))]
    levels = [206, 186, 169, 146, 128, 104, 72]
    base, now = 232, 5
    out = []
    rnd = random.Random(5)

    def step_path(i0, i1, start):
        p = f"M{start[0]:.1f} {start[1]:.1f}"
        prev = start[1]
        for i in range(i0, i1 + 1):
            p += f"H{xs[i] - 26:.1f}C{xs[i] - 10:.1f} {prev:.1f} {xs[i] - 14:.1f} {levels[i]:.1f} {xs[i]:.1f} {levels[i]:.1f}"
            prev = levels[i]
        return p

    solid = step_path(0, now, (34, 218))
    area = gradient(d, 0, 60, 0, base, [(0, t["accent"], .2), (1, t["accent"], 0)])
    out.append(f'<path d="{solid}H{xs[now] + 34:.1f}V{base}H34Z" fill="url(#{area})"/>')
    # attempts: everything that scored below the best-so-far
    for i in range(now + 1):
        lo = 34 if i == 0 else xs[i - 1]
        ceiling = 218 if i == 0 else levels[i - 1]
        for _ in range(16):
            x, y = rnd.uniform(lo + 4, xs[i] - 4), rnd.uniform(ceiling + 7, base - 5)
            o = rnd.uniform(.3, .7)
            tw = ""
            if rnd.random() < .18:
                tw = (f'<animate attributeName="opacity" values="{o:.2f};.05;{o:.2f}" dur="{rnd.uniform(3, 6):.1f}s" '
                      f'begin="-{rnd.uniform(0, 6):.1f}s" repeatCount="indefinite"/>')
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rnd.uniform(1.1, 2.1):.2f}" fill="{t["muted"]}" '
                       f'opacity="{o:.2f}">{tw}</circle>')
    out.append(f'<path d="M34 {base}H{W - 34}" stroke="{t["line"]}"/>')
    out.append(f'<path d="{solid}H{xs[now] + 34:.1f}" fill="none" stroke="{t["accent"]}" stroke-width="2" '
               f'stroke-linecap="round"/>')
    projection = step_path(now + 1, len(xs) - 1, (xs[now] + 34, levels[now])) + f"H{W - 34}"
    out.append(f'<path d="{projection}" fill="none" stroke="{t["accent"]}" stroke-width="1.6" '
               f'stroke-dasharray="3 5" opacity=".75"/>')
    out.append(f'<g opacity="0"><circle r="7" fill="{t["accent"]}" opacity=".25"/><circle r="3" fill="{t["accent"]}"/>'
               f'<animateMotion dur="7s" repeatCount="indefinite" path="{solid}"/>'
               f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;.06;.88;1" dur="7s" '
               f'repeatCount="indefinite"/></g>')
    rows = []
    for i, (when, title, detail) in enumerate(GENERATIONS):
        x, y = xs[i], levels[i]
        out.append(f'<path d="M{x:.1f} {base}v5" stroke="{t["muted"]}"/>')
        if i < now:
            out.append(f'<circle cx="{x:.1f}" cy="{y}" r="4.6" fill="{t["panel"]}" stroke="{t["accent"]}" stroke-width="1.6"/>'
                       f'<circle cx="{x:.1f}" cy="{y}" r="1.8" fill="{t["accent"]}"/>')
        elif i == now:
            out.append(pulse(x, y, t["accent"], r=4.4, dur=2.2))
        else:
            out.append(f'<circle cx="{x:.1f}" cy="{y}" r="7" fill="{t["panel"]}" stroke="{t["muted"]}" '
                       f'stroke-dasharray="2 2.5"/>')
            out.append(d.text(MONO, "?", 9, x, y + 3.2, t["muted"], anchor="middle"))
        out.append(d.text(MONO, f"GEN {i + 1:02d} · {when}", 8.5, x, base + 24, t["muted"], track=.1, anchor="middle"))
        tl, dl = wrap(SANS6, title, 12, 114), wrap(SANS4, detail, 10.5, 112)
        rows.append(len(tl) * 16 + len(dl) * 14.5)
        color = t["accent"] if i == len(GENERATIONS) - 1 else t["ink"]
        for j, line in enumerate(tl):
            out.append(d.text(SANS6, line, 12, x, base + 46 + j * 16, color, anchor="middle"))
        for j, line in enumerate(dl):
            out.append(d.text(SANS4, line, 10.5, x, base + 46 + len(tl) * 16 + 2 + j * 14.5, t["muted"], anchor="middle"))
    out.append(f'<path d="M34 30h16" stroke="{t["accent"]}" stroke-width="2"/>')
    out.append(d.text(MONO, "BEST-SO-FAR", 8.5, 58, 33, t["muted"], track=.14))
    out.append(f'<circle cx="158" cy="30" r="1.8" fill="{t["muted"]}"/>')
    out.append(d.text(MONO, "ATTEMPTS", 8.5, 166, 33, t["muted"], track=.14))
    out.append(d.text(MONO, "f*(t)  ·  GENERATIONS 01 → 07", 8.5, W - 34, 33, t["muted"], track=.14, anchor="end"))
    d.h = base + 46 + max(rows) + 18
    frame(d, t["panel"])
    d.add(*out)
    border(d, t)
    return d.svg()


# ── footer ────────────────────────────────────────────────────────────────

def footer(t):
    W, H = 880, 250
    d = Doc(W, H, "Thanks for reading — let's turn complexity into clarity. A badminton rally, "
                  "drawn with real shuttlecock physics.")
    clip = frame(d, t["bg"], rx=18)
    out = [f'<g clip-path="url(#{clip})">']
    if t["name"] == "light":
        out.append(f'<rect width="{W}" height="{H}" fill="url(#{grid(d, t["grid"])})"/>')
    v0, path = clear_shot()
    apex = max(p[2] for p in path)
    ground = 194
    k = min(32.0, (ground - 30) / apex)

    def X(m):
        return 440 + (m - 6.7) * k

    def Y(m):
        return ground - m * k

    # court, side-on: floor, net, line positions
    out.append(f'<path d="M{X(-1.2):.1f} {ground}H{X(14.6):.1f}" stroke="{t["muted"]}" stroke-width="1.2"/>')
    ticks = "".join(f"M{X(m):.1f} {ground}v6" for m in (0, .76, 6.7 - 1.98, 6.7 + 1.98, 13.4 - .76, 13.4))
    out.append(f'<path d="{ticks}" stroke="{t["muted"]}"/>')
    net = d.uid("net")
    d.define(f'<pattern id="{net}" width="4" height="4" patternUnits="userSpaceOnUse">'
             f'<path d="M0 0L4 4M4 0L0 4" stroke="{t["muted"]}" stroke-width=".5"/></pattern>')
    out.append(f'<rect x="{X(6.7) - 1.5:.1f}" y="{Y(1.55):.1f}" width="3" height="{.76 * k:.1f}" fill="url(#{net})"/>')
    out.append(f'<path d="M{X(6.7):.1f} {ground}V{Y(1.55) - 2:.1f}" stroke="{t["ink2"]}" stroke-width="1.6"/>')
    # what intuition expects (a parabola) against what air does
    para = [(X(1 + m), Y(2.3 + (apex - 2.3) * (1 - ((m - 5.7) / 5.7) ** 2)))
            for m in (11.4 * i / 60 for i in range(61))]
    out.append(f'<path d="{path_from(para)}" fill="none" stroke="{t["faint"]}" stroke-dasharray="3 5"/>')
    shot1 = [(X(1 + p[1]), Y(p[2])) for p in path]
    shot2 = [(X(12.4 - p[1]), Y(p[2])) for p in path]
    jnu = t["jnu"]
    out.append(f'<path d="{path_from(shot1)}" fill="none" stroke="{jnu}" stroke-width="1.4"/>')
    for (x, y), side in ((shot1[0], 1), (shot2[0], -1)):   # a racket at each hitting point
        out.append(f'<g transform="translate({x - side * 4:.1f} {y + 2:.1f}) rotate({-side * 24})" fill="none" '
                   f'stroke="{t["muted"]}" stroke-width="1.1"><ellipse rx="5" ry="7.5"/>'
                   f'<path d="M0 7.5V25" stroke-width="1.6" stroke-linecap="round"/></g>')
    sid = shuttle_def(d)
    for i in range(0, len(path) - 1, 4):   # stroboscope
        p, (x, y) = path[i], shot1[i]
        ang = math.degrees(math.atan2(-p[4], p[3]))
        out.append(f'<use xlink:href="#{sid}" transform="translate({x:.1f} {y:.1f}) rotate({ang:.0f})" '
                   f'fill="{t["ink2"]}" stroke="{t["ink2"]}" opacity="{.1 + .3 * i / len(path):.2f}"/>')
    T1 = path[-1][0]
    slow = 1.6
    pts = shot1 + shot2[1:]
    times = [p[0] for p in path] + [T1 + p[0] for p in path[1:]]
    kt, kp = motion_keys(times, pts)
    out.append(f'<g fill="{t["ink"]}" stroke="{t["ink"]}" opacity="0"><use xlink:href="#{sid}" transform="scale(1.25)"/>'
               f'<animateMotion dur="{2 * T1 * slow:.2f}s" repeatCount="indefinite" rotate="auto" calcMode="linear" '
               f'keyTimes="{kt}" keyPoints="{kp}" path="{path_from(pts)}"/>{SHOW}</g>')
    for (x, y), when in ((shot1[0], 0.0), (shot2[0], .5)):
        kt_hit = "0;.08;1" if when == 0 else "0;.5;.58;1"
        r_vals = "2;16;16" if when == 0 else "2;2;16;16"
        o_vals = ".8;0;0" if when == 0 else "0;.8;0;0"
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2" fill="none" stroke="{jnu}" stroke-width="1.2">'
                   f'<animate attributeName="r" values="{r_vals}" keyTimes="{kt_hit}" dur="{2 * T1 * slow:.2f}s" repeatCount="indefinite"/>'
                   f'<animate attributeName="opacity" values="{o_vals}" keyTimes="{kt_hit}" dur="{2 * T1 * slow:.2f}s" repeatCount="indefinite"/></circle>')
    # annotations
    px, py = para[30]
    out.append(d.text(SERIF, "intuition", 14, px - 8, py - 9, t["muted"], anchor="end"))
    steep = shot1[int(len(shot1) * .9)]
    out.append(f'<path d="M{steep[0] + 4:.1f} {steep[1]:.1f}H{steep[0] + 34:.1f}" stroke="{t["muted"]}" stroke-width=".8"/>')
    out.append(d.text(SERIF, "air", 14, steep[0] + 39, steep[1] + 4, jnu))
    out.append(d.text(MONO, "quadratic drag: the fall is", 8.5, steep[0] + 39, steep[1] + 18, t["muted"], track=.04))
    out.append(d.text(MONO, "steeper than the climb", 8.5, steep[0] + 39, steep[1] + 30, t["muted"], track=.04))
    out.append(d.text(MONO, "CLEAR", 9, W - 150, 46, t["ink2"], track=.06))
    rows = [("v", "0", f"= {v0:.1f} m/s"), ("θ", "", "= 30°"), ("v", "t", "= 6.8 m/s"), ("t", "", f"= {T1:.2f} s")]
    for i, (sym, sub, value) in enumerate(rows, 1):
        out.append(text_sub(d, MONO, sym, sub, 9, W - 150, 46 + i * 15, t["muted"]))
        out.append(d.text(MONO, value, 9, W - 128, 46 + i * 15, t["muted"], track=.06))
    out.append(d.text(SERIF, "Thanks for reading —", 23, 36, 62, t["ink"]))
    out.append(d.text(SERIF, "let’s turn complexity", 23, 36, 90, t["ink2"]))
    out.append(d.text(SERIF, "into clarity.", 23, 36, 118, t["ink2"]))
    out.append(d.text(MONO, "JNU BADMINTON CLUB  ·  PRESIDENT  ·  THE SHUTTLE IS ALWAYS IN THE AIR", 8.5,
                      W / 2, H - 22, t["muted"], track=.2, anchor="middle"))
    out.append("</g>")
    d.add(*out)
    border(d, t, rx=18)
    return d.svg()


# ── avatar ────────────────────────────────────────────────────────────────

def avatar(t):
    """The portfolio's ZG monogram over the lit limb, for the account picture.
    Upload a PNG of it; GitHub crops avatars to a circle."""
    S = 460
    d = Doc(S, S, "ZG — Zhang Guohao")
    out = [f'<rect width="{S}" height="{S}" fill="url(#{radial(d, 330, 90, 470, [(0, t["bg2"], 1), (1, t["bg"], 1)])})"/>']
    CX, CY, R = 520, 900, 560
    rnd = random.Random(4)
    for _ in range(80):
        x, y = rnd.uniform(4, S - 4), rnd.uniform(4, S - 4)
        if math.hypot(x - CX, y - CY) > R + 4 and not (90 < x < 370 and 140 < y < 300):
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rnd.uniform(.4, 1.2):.2f}" fill="{t["star"]}" '
                       f'opacity="{rnd.uniform(.2, .85):.2f}"/>')
    p0, p1, p2, p3 = t["planet"]
    fill = radial(d, CX, CY, R, [(0, p0, 1), (.84, p1, 1), (.962, p2, 1), (1, p3, 1)])
    limb = gradient(d, 150, 470, 470, 330, [(0, t["limb"], .1), (1, t["limb"], 1)])
    haze = gradient(d, 150, 470, 470, 330, [(0, t["glow"], 0), (1, t["glow"], .9)])
    arc = circle_arc(CX, CY, R, S + 40, S + 40)
    out.append(f'<path d="{arc}" fill="none" stroke="url(#{haze})" stroke-width="40" opacity=".55" '
               f'filter="url(#{blur(d, 13)})"/>')
    out.append(f'<circle cx="{CX}" cy="{CY}" r="{R}" fill="url(#{fill})"/>')
    out.append(f'<path d="{arc}" fill="none" stroke="url(#{haze})" stroke-width="6" filter="url(#{blur(d, 4)})"/>')
    out.append(f'<path d="{arc}" fill="none" stroke="url(#{limb})" stroke-width="2"/>')
    out.append(f'<path d="{circle_arc(CX, CY, R + 36, S + 40, S + 40)}" fill="none" stroke="{t["muted"]}" '
               f'stroke-width="1.6" stroke-dasharray="0 8" stroke-linecap="round" opacity=".8"/>')
    a = math.radians(-118)
    sx, sy = CX + (R + 36) * math.cos(a), CY + (R + 36) * math.sin(a)
    out.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="9" fill="{t["accent"]}" opacity=".25"/>'
               f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="3.2" fill="{t["ink"]}"/>')
    out.append(d.text(SANS7, "ZG", 176, S / 2, 286, t["ink"], track=.04, anchor="middle"))
    d.add(*out)
    return d.svg()


# ── preview ───────────────────────────────────────────────────────────────

PREVIEW = r"""<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Y1tong profile preview</title>
<link id="md-light" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/github-markdown-css@5.5.1/github-markdown-light.css">
<link id="md-dark" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/github-markdown-css@5.5.1/github-markdown-dark.css" disabled>
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<script>window.MathJax = { svg: { fontCache: "global" } };</script>
<script defer src="https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-svg.js"></script>
<style>
  :root { --bg: #ffffff; --fg: #1f2328; --muted: #59636e; --border: #d1d9e0; --bar: #f6f8fa; }
  [data-theme="dark"] { --bg: #0d1117; --fg: #f0f6fc; --muted: #9198a1; --border: #3d444d; --bar: #010409; }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--fg);
         font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif; }
  .bar { display: flex; align-items: center; gap: 8px; padding: 10px 16px; background: var(--bar);
         border-bottom: 1px solid var(--border); font-size: 12px; color: var(--muted); }
  .bar span { flex: 1; }
  .bar button { font: inherit; padding: 4px 12px; border-radius: 6px; border: 1px solid var(--border);
                background: transparent; color: var(--fg); cursor: pointer; }
  .bar button[aria-pressed="true"] { background: var(--fg); color: var(--bg); }
  .page { max-width: 1280px; margin: 0 auto; padding: 24px 32px; display: flex; gap: 24px; align-items: flex-start; }
  .side { width: 296px; flex: none; }
  .side img { width: 100%; aspect-ratio: 1; border-radius: 50%; border: 1px solid var(--border); display: block; }
  .side h1 { margin: 16px 0 0; font-size: 24px; line-height: 1.25; font-weight: 600; }
  .side p { margin: 0; font-size: 20px; font-weight: 300; color: var(--muted); }
  .main { flex: 1; min-width: 0; }
  .readme { border: 1px solid var(--border); border-radius: 6px; padding: 24px; }
  .readme-title { font: 12px ui-monospace, SFMono-Regular, Consolas, monospace; color: var(--muted); margin-bottom: 16px; }
  .markdown-body { background: transparent !important; }
  .math { overflow-x: auto; margin: 16px 0; }
  @media (max-width: 1011px) {
    .page { flex-direction: column; padding: 16px; }
    .side { width: 100%; display: flex; gap: 16px; align-items: center; }
    .side img { width: 72px; }
    .side h1 { margin: 0; }
  }
</style>
</head>
<body>
<div class="bar">
  <span>Local preview of github.com/Y1tong (marked + MathJax; close to GitHub, not identical)</span>
  <button data-theme="light" aria-pressed="true">Light</button>
  <button data-theme="dark" aria-pressed="false">Dark</button>
</div>
<div class="page">
  <aside class="side">
    <img src="https://avatars.githubusercontent.com/u/326085461?v=4" alt="">
    <div><h1>Zhang Guohao</h1><p>Y1tong</p></div>
  </aside>
  <main class="main">
    <div class="readme">
      <div class="readme-title">Y1tong / README.md</div>
      <article id="readme" class="markdown-body"></article>
    </div>
  </main>
</div>
<script type="text/markdown" id="source">%README%</script>
<script>
  const source = document.getElementById("source").textContent;
  const out = document.getElementById("readme");
  out.innerHTML = marked.parse(
    source.replace(/```math\n([\s\S]*?)```/g, (_, tex) => `<div class="math">\\[${tex}\\]</div>`));
  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    document.getElementById("md-light").disabled = theme !== "light";
    document.getElementById("md-dark").disabled = theme !== "dark";
    // GitHub picks <picture> sources by prefers-color-scheme; force the choice here
    out.querySelectorAll("picture source").forEach(s => { s.media = theme === "dark" ? "all" : "not all"; });
    document.querySelectorAll(".bar button").forEach(b => b.setAttribute("aria-pressed", b.dataset.theme === theme));
  }
  document.querySelectorAll(".bar button").forEach(b => b.addEventListener("click", () => setTheme(b.dataset.theme)));
  setTheme(new URLSearchParams(location.search).get("theme") || "light");
</script>
</body>
</html>
"""


def preview():
    md = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "</script" not in md
    (ROOT / "preview.html").write_text(PREVIEW.replace("%README%", md), encoding="utf-8", newline="\n")


# ── main ──────────────────────────────────────────────────────────────────

def main():
    global SANS4, SANS5, SANS6, SANS7, SERIF, MONO, CJK_SERIF, CJK_SANS
    mono = Font("fm", font_file("FiraMono-Regular.otf", "fira"))
    hei = Font("fh", font_file("FandolHei-Regular.otf", "fandol"))
    song = Font("fs", font_file("FandolSong-Regular.otf", "fandol"))
    sans = {w: Font(f"m{w}", FONTS / "Manrope-VF.ttf", w) for w in (400, 500, 600, 700)}
    SANS4, SANS5, SANS6, SANS7 = ([sans[w], mono, hei] for w in (400, 500, 600, 700))
    SERIF = [Font("si", FONTS / "InstrumentSerif-Italic.ttf"), sans[400], mono, song]
    MONO = [mono, sans[400], hei]
    CJK_SERIF, CJK_SANS = [song], [hei]

    jobs = {"header": header, "card-ieltsspeak": flagship, "toolkit": toolkit,
            "convergence": convergence, "footer": footer}
    for i, spec in enumerate(CARDS):
        jobs[f'card-{spec["slug"]}'] = lambda t, spec=spec, col=i % 2: grid_card(t, spec, col)
    ASSETS.mkdir(exist_ok=True)
    for name, build in jobs.items():
        for theme in (LIGHT, DARK):
            path = ASSETS / f'{name}-{theme["name"]}.svg'
            path.write_text(build(theme), encoding="utf-8", newline="\n")
            print(f"{path.relative_to(ROOT)}  {path.stat().st_size / 1024:.0f} KB")
    (ASSETS / "avatar.svg").write_text(avatar(DARK), encoding="utf-8", newline="\n")
    if (ROOT / "README.md").exists():
        preview()
        print("preview.html")


if __name__ == "__main__":
    main()
