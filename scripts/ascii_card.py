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

from PIL import Image, ImageDraw, ImageFilter, ImageOps

COLS, ROWS = 48, 26
RAMP = " .:-=+*#%@"

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
    "dark": dict(bg="#0d1117", border="#30363d", ascii="#8b949e", key="#ffa657",
                 val="#a5d6ff", title="#3b82f6", rule="#6e7681", dot="#6e7681"),
    "light": dict(bg="#ffffff", border="#d0d7de", ascii="#57606a", key="#953800",
                  val="#0a3069", title="#1f3b73", rule="#8c959f", dot="#8c959f"),
}


def fetch(url, token=None):
    req = urllib.request.Request(url, headers={"User-Agent": "ascii-card"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def avatar_ascii(img):
    """Line-art friendly conversion: keeps strokes, drops the round frame."""
    img = ImageOps.exif_transpose(img).convert("L").resize((440, 440), Image.LANCZOS)
    w, h = img.size
    # Keep only the inner disc of the avatar (GitHub avatars are often framed by a ring).
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse((w * 0.13, h * 0.13, w * 0.87, h * 0.87), fill=255)
    # Strokes are whatever differs most from the dominant background tone.
    hist, acc, bg = img.histogram(), 0, 0
    for bg, count in enumerate(hist):  # median tone = background
        acc += count
        if acc >= w * h / 2:
            break
    diff = Image.eval(img, lambda v: min(255, abs(v - bg) * 2))
    diff = Image.composite(diff, Image.new("L", img.size, 0), mask)
    # Thicken thin strokes so they survive the downscale.
    diff = diff.filter(ImageFilter.MaxFilter(7))
    diff = ImageOps.autocontrast(diff, cutoff=1)
    small = diff.resize((COLS, ROWS), Image.BOX)
    px = small.load()
    n = len(RAMP) - 1
    lines = ["".join(RAMP[min(n, int((px[x, y] / 255) ** 0.8 * n))] for x in range(COLS)) for y in range(ROWS)]
    # Trim empty rows top/bottom.
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


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
    left_x, right_x, top = 25, 420, 35
    width = 985
    height = max(len(ascii_lines), len(INFO)) * lh + top + 10
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
    a_top = top + max(0, len(INFO) - len(ascii_lines)) * lh // 2
    for i, line in enumerate(ascii_lines):
        out.append(
            f'<text class="l" style="animation-delay:{i*0.04:.2f}s" x="{left_x}" y="{a_top + i*lh}" '
            f'fill="{t["ascii"]}" xml:space="preserve">{escape(line)}</text>'
        )

    base = len(ascii_lines) * 0.04
    y = top
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
    lines = avatar_ascii(Image.open(io.BytesIO(raw)))
    stats = github_stats(user, token) if not src else {"Repos": 12, "Stars": 34, "Followers": 56}
    for name, theme in THEMES.items():
        with open(os.path.join(out_dir, f"ascii-card-{name}.svg"), "w", encoding="utf-8") as f:
            f.write(build_svg(lines, stats, theme))


if __name__ == "__main__":
    main()
