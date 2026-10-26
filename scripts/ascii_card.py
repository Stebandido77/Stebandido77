"""Build a neofetch-style SVG card: ASCII art of the GitHub avatar + profile info.

Runs inside GitHub Actions (needs network). Usage:
    python scripts/ascii_card.py <username> <out_dir>
"""
import io
import json
import os
import sys
import urllib.request
from xml.sax.saxutils import escape

from PIL import Image, ImageFilter, ImageOps

COLS = 74

INFO = [
    ("title", "esteban@labastidas"),
    ("rule", ""),
    ("kv", "Location", "Bogotá, Colombia"),
    ("kv", "Role", "Strategy & Investor Relations @ Grupo Aval"),
    ("kv", "Focus", "M&A valuation · corporate finance"),
    ("kv", "Research", "Impact evaluation · education · fintech"),
    ("blank",),
    ("kv", "Education.MSc", "Applied Economics — Uniandes"),
    ("kv", "Education.MSc", "Finance — EUDE Business School"),
    ("kv", "Education.BSc", "Ind. Engineering & Economics — Javeriana"),
    ("kv", "Certs", "CMSA®"),
    ("blank",),
    ("kv", "Languages.Code", "Python, R, Stata, SQL, VBA, LaTeX"),
    ("kv", "Languages.Real", "Spanish, English"),
    ("kv", "Motto", "Derivatives by day, Batman by night"),
    ("blank",),
    ("section", "Contact"),
    ("kv", "LinkedIn", "esteban-labastidas-cmsa"),
    ("kv", "X", "@Stebandido77"),
    ("kv", "Web", "stebandido77.github.io"),
    ("blank",),
    ("section", "GitHub Stats"),
    ("stats",),
]

THEMES = {
    "dark": dict(bg="#0d1117", border="#30363d", ascii="#c9d1d9", key="#ffa657",
                 val="#a5d6ff", title="#3b82f6", rule="#6e7681", dot="#6e7681"),
    "light": dict(bg="#ffffff", border="#d0d7de", ascii="#24292f", key="#953800",
                  val="#0a3069", title="#1f3b73", rule="#8c959f", dot="#8c959f"),
}


def fetch(url, token=None):
    req = urllib.request.Request(url, headers={"User-Agent": "ascii-card"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


# Fine text grid for the portrait: ASCII_FS px glyphs, ASCII_LH px lines.
ASCII_FS, ASCII_LH = 10, 12
CELL_W, CELL_H = 6, 12  # sampling cell, matches the glyph aspect (0.6em x line height)
RAMP = " .:-=+*#%@"


def _stroke_map(img):
    """Map of the drawing's strokes: light lines inside the avatar's dark disc."""
    img = ImageOps.exif_transpose(img).convert("L").resize((800, 800), Image.LANCZOS)
    dark = img.point(lambda v: 255 if v < 128 else 0)
    # Close the thin strokes so the disc becomes solid, then shrink it off its rim.
    disc = dark.filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.MinFilter(15))
    disc = disc.filter(ImageFilter.MinFilter(9))
    if not disc.getbbox():  # not a dark-disc avatar: fall back to whole image
        disc = Image.new("L", img.size, 255)
    strokes = img.point(lambda v: 255 if v >= 128 else 0)
    strokes = Image.composite(strokes, Image.new("L", img.size, 0), disc)
    bbox = strokes.getbbox() or (0, 0, *img.size)
    x0, y0, x1, y1 = bbox
    m = 12
    strokes = strokes.crop((max(0, x0 - m), max(0, y0 - m), x1 + m, y1 + m))
    # Fit the crop to COLS x ROWS text cells (cells are twice as tall as wide).
    w, h = strokes.size
    rows = max(8, round(COLS * CELL_W * h / w / CELL_H))
    strokes = strokes.filter(ImageFilter.MaxFilter(3))
    strokes = strokes.resize((COLS * CELL_W, rows * CELL_H), Image.LANCZOS)
    return strokes.filter(ImageFilter.GaussianBlur(0.8)), rows


def avatar_ascii(img):
    """Dense line-art conversion: small glyphs on a fine grid, weighted by stroke coverage."""
    strokes, rows = _stroke_map(img)
    small = strokes.resize((COLS, rows), Image.BOX)
    px = small.load()
    n = len(RAMP) - 1
    lines = []
    for y in range(rows):
        row = []
        for x in range(COLS):
            v = px[x, y] / 255
            row.append(" " if v < 0.06 else RAMP[max(1, min(n, round(v ** 0.6 * n)))])
        lines.append("".join(row).rstrip())
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    pad = min(len(l) - len(l.lstrip()) for l in lines if l.strip())
    return [l[pad:] for l in lines]


def github_stats(user, token):
    try:
        u = json.loads(fetch(f"https://api.github.com/users/{user}", token))
        repos = json.loads(fetch(f"https://api.github.com/users/{user}/repos?per_page=100&type=owner", token))
        stars = sum(r.get("stargazers_count", 0) for r in repos)
        return {"Repos": u.get("public_repos", "—"), "Stars": stars, "Followers": u.get("followers", "—")}
    except Exception as exc:  # keep the card even if the API fails
        print(f"stats unavailable: {exc}", file=sys.stderr)
        return {"Repos": "—", "Stars": "—", "Followers": "—"}


def build_svg(ascii_lines, stats, t):
    fs, lh = 15, 20
    left_x, top = 25, 35
    art_w = max(len(l) for l in ascii_lines) * ASCII_FS * 0.6
    right_x = int(left_x + art_w + 35)
    width = right_x + 565
    art_h = len(ascii_lines) * ASCII_LH
    info_h = len(INFO) * lh
    height = max(art_h, info_h) + top + 10
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'font-family="ui-monospace, SFMono-Regular, Consolas, \'Liberation Mono\', monospace" font-size="{fs}px">',
        "<style>",
        ".l{opacity:0;animation:in .45s ease-out forwards}",
        "@keyframes in{from{opacity:0;transform:translateX(-6px)}to{opacity:1;transform:none}}",
        ".cur{animation:blink 1s steps(1) infinite}",
        "@keyframes blink{50%{opacity:0}}",
        "</style>",
        f'<rect width="{width}" height="{height}" rx="15" fill="{t["bg"]}" stroke="{t["border"]}"/>',
    ]
    a_top = top - 8 + max(0, info_h - art_h) // 2
    i_top = top + max(0, art_h - info_h) // 2
    for i, line in enumerate(ascii_lines):
        out.append(
            f'<text class="l" style="animation-delay:{i*0.025:.2f}s" x="{left_x}" y="{a_top + i*ASCII_LH}" font-size="{ASCII_FS}px" '
            f'fill="{t["ascii"]}" xml:space="preserve">{escape(line)}</text>'
        )

    base = 0.3
    y = i_top
    for i, row in enumerate(INFO):
        delay = f"animation-delay:{base + i*0.07:.2f}s"
        kind = row[0]
        if kind == "title":
            out.append(f'<text class="l" style="{delay}" x="{right_x}" y="{y}" fill="{t["title"]}" font-weight="bold">'
                       f'{escape(row[1])}<tspan class="cur">▌</tspan></text>')
        elif kind == "rule":
            out.append(f'<text class="l" style="{delay}" x="{right_x}" y="{y}" fill="{t["rule"]}">{"—" * 52}</text>')
        elif kind == "section":
            out.append(f'<text class="l" style="{delay}" x="{right_x}" y="{y}" fill="{t["title"]}" font-weight="bold">'
                       f'- {escape(row[1])} {"—" * (46 - len(row[1]))}</text>')
        elif kind == "kv":
            key, val = row[1], row[2]
            dots = "." * max(2, 17 - len(key))
            out.append(f'<text class="l" style="{delay}" x="{right_x}" y="{y}" xml:space="preserve">'
                       f'<tspan fill="{t["key"]}">{escape(key)}</tspan><tspan fill="{t["dot"]}">:{dots} </tspan>'
                       f'<tspan fill="{t["val"]}">{escape(val)}</tspan></text>')
        elif kind == "stats":
            parts = []
            for k, v in stats.items():
                parts.append(f'<tspan fill="{t["key"]}">{k}</tspan><tspan fill="{t["dot"]}">: </tspan>'
                             f'<tspan fill="{t["val"]}">{v}</tspan><tspan fill="{t["dot"]}">   </tspan>')
            out.append(f'<text class="l" style="{delay}" x="{right_x}" y="{y}" xml:space="preserve">{"".join(parts)}</text>')
        y += lh
    out.append("</svg>")
    return "\n".join(out)


def main():
    user, out_dir = sys.argv[1], sys.argv[2]
    token = os.environ.get("GITHUB_TOKEN")
    os.makedirs(out_dir, exist_ok=True)
    src = os.environ.get("AVATAR_FILE")
    raw = open(src, "rb").read() if src else fetch(f"https://github.com/{user}.png?size=400")
    with open(os.path.join(out_dir, "avatar.png"), "wb") as f:
        f.write(raw)
    lines = avatar_ascii(Image.open(io.BytesIO(raw)))
    stats = github_stats(user, token) if not src else {"Repos": 12, "Stars": 34, "Followers": 56}
    for name, theme in THEMES.items():
        with open(os.path.join(out_dir, f"ascii-card-{name}.svg"), "w", encoding="utf-8") as f:
            f.write(build_svg(lines, stats, theme))


if __name__ == "__main__":
    main()
