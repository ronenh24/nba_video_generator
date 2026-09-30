"""Build a 1280x720 highlight thumbnail: headshot + name + key stat tiles.

Requires: pip install pillow
Reads the same stat-row dicts that scraper.parse_boxscore() returns
(keys like PTS, REB, AST, STL, BLK, FGM, FGA, IMAGE_URL, PLAYER_ID ...).
"""
import base64
import functools
import io
import os
import re
import urllib.request

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720

# Optional: set this to a .ttf you like (e.g. Impact / Bebas Neue).
FONT_PATH = None
_FONT_CANDIDATES = [
    "impact.ttf", "Impact.ttf", "arialbd.ttf", "Arial Bold.ttf",
    "DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

# Primary team colors by abbreviation (approximate).
TEAM_COLORS = {
    "atl": "#C8102E", "bos": "#007A33", "bkn": "#444444", "cha": "#1D8FA8",
    "chi": "#CE1141", "cle": "#860038", "dal": "#0064B1", "den": "#1D428A",
    "det": "#C8102E", "gsw": "#1D428A", "hou": "#CE1141", "ind": "#FDBB30",
    "lac": "#C8102E", "lal": "#552583", "mem": "#5D76A9", "mia": "#98002E",
    "mil": "#00471B", "min": "#236192", "nop": "#0C2340", "nyk": "#F58426",
    "okc": "#007AC1", "orl": "#0077C0", "phi": "#006BB6", "phx": "#E56020",
    "por": "#E03A3E", "sac": "#5A2D81", "sas": "#8A8D8F", "tor": "#CE1141",
    "uta": "#4E2A84", "was": "#E31837",
}
DEFAULT_COLOR = "#1D428A"


@functools.lru_cache(maxsize=None)
def _font(size: int):
    for path in ([FONT_PATH] if FONT_PATH else []) + _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _num(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _get(row: dict, *keys: str) -> str:
    for k in keys:
        if row.get(k) not in (None, ""):
            return str(row[k])
    return ""


# --------------------------------------------------------------------------
# Which stats to show
# --------------------------------------------------------------------------
def pick_stats(row: dict) -> list[tuple[str, int]]:
    """PTS always, plus the 3 most notable of REB/AST/STL/BLK/3PM."""
    pts = _num(_get(row, "PTS"))
    # (label, value, "impressive" threshold)
    others = [
        ("REB", _num(_get(row, "REB")), 8),
        ("AST", _num(_get(row, "AST")), 8),
        ("STL", _num(_get(row, "STL")), 3),
        ("BLK", _num(_get(row, "BLK")), 3),
        ("3PM", _num(_get(row, "3PM", "FG3M")), 5),
    ]
    others.sort(key=lambda t: t[1] / t[2], reverse=True)
    return [("PTS", pts)] + [(lbl, val) for lbl, val, _ in others[:3]]


def badge_text(row: dict) -> str:
    cats = [_num(_get(row, k)) for k in ("PTS", "REB", "AST", "STL", "BLK")]
    tens = sum(c >= 10 for c in cats)
    pts = cats[0]
    if tens >= 4:
        return "QUADRUPLE-DOUBLE"
    if tens == 3:
        return "TRIPLE-DOUBLE"
    if pts >= 50:
        return f"{pts}-POINT GAME"
    if pts >= 40:
        return "40-PIECE"
    if tens == 2:
        return "DOUBLE-DOUBLE"
    return "HIGHLIGHTS"


def _footer(row: dict) -> str:
    bits = []
    fgm, fga = _get(row, "FGM"), _get(row, "FGA")
    if fgm and fga:
        bits.append(f"{fgm}/{fga} FG")
    tpm, tpa = _get(row, "3PM", "FG3M"), _get(row, "3PA", "FG3A")
    if tpm and tpa:
        bits.append(f"{tpm}/{tpa} 3PT")
    ftm, fta = _get(row, "FTM"), _get(row, "FTA")
    if ftm and fta:
        bits.append(f"{ftm}/{fta} FT")
    return "  •  ".join(bits)


# --------------------------------------------------------------------------
# Drawing helpers
# --------------------------------------------------------------------------
def headshot_url(row: dict) -> str:
    url = _get(row, "IMAGE_URL")
    if not url and _get(row, "PLAYER_ID"):
        url = f"https://cdn.nba.com/headshots/nba/latest/1040x760/{row['PLAYER_ID']}.png"
    return url


def fetch_image_via_browser(driver, url: str) -> bytes | None:
    """Download an image using the live Selenium session (same cookies,
    headers and origin as nba.com itself), which gets past CDN blocking of
    plain Python HTTP clients. Call while the driver is still open and sitting
    on an nba.com page. Returns raw bytes, or None on failure."""
    script = """
    const done = arguments[arguments.length - 1];
    fetch(arguments[0])
      .then(r => { if (!r.ok) throw new Error(r.status); return r.blob(); })
      .then(b => {
        const fr = new FileReader();
        fr.onloadend = () => done(fr.result.split(',')[1]);
        fr.readAsDataURL(b);
      })
      .catch(() => done(null));
    """
    try:
        driver.set_script_timeout(15)
        b64 = driver.execute_async_script(script, url)
        return base64.b64decode(b64) if b64 else None
    except Exception as e:
        print(f"    ! browser image fetch failed ({e.__class__.__name__})")
        return None


def attach_headshot(driver, row: dict) -> None:
    """Fetch the headshot through the browser and stash the bytes on the row."""
    url = headshot_url(row)
    if url and not row.get("HEADSHOT_BYTES"):
        data = fetch_image_via_browser(driver, url)
        if data:
            row["HEADSHOT_BYTES"] = data


def _fetch_headshot(row: dict):
    # 1) bytes already downloaded through the browser
    data = row.get("HEADSHOT_BYTES")

    # 2) fallback: plain request with browser-like headers
    if not data:
        url = headshot_url(row)
        if not url:
            return None
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/124.0 Safari/537.36"),
                "Referer": "https://www.nba.com/",
                "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
        except Exception as e:
            print(f"    ! headshot fetch failed ({e.__class__.__name__}); continuing without it")
            return None

    try:
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        print(f"    ! headshot decode failed ({e.__class__.__name__}); continuing without it")
        return None


def _background(color: tuple[int, int, int]) -> Image.Image:
    """Dark on the left (for text), team color glowing on the right."""
    dark = (12, 14, 20)
    mask = Image.new("L", (W, H))
    d = ImageDraw.Draw(mask)
    for x in range(W):
        t = max(0.0, (x - W * 0.25) / (W * 0.75))
        d.line([(x, 0), (x, H)], fill=int(255 * min(1.0, t) ** 1.3))
    base = Image.new("RGB", (W, H), dark)
    return Image.composite(Image.new("RGB", (W, H), color), base, mask).convert("RGBA")


def _fit_font(draw, text: str, max_width: int, start: int, minimum: int = 60):
    size = start
    while size > minimum:
        f = _font(size)
        if draw.textlength(text, font=f) <= max_width:
            return f
        size -= 6
    return _font(minimum)


def _text(draw, xy, text, font, fill="white", stroke=0):
    draw.text(xy, text, font=font, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))


def _split_name(name: str) -> tuple[str, str]:
    parts = name.split()
    if len(parts) > 1 and parts[-1] in {"Jr.", "Sr.", "II", "III", "IV"}:
        return " ".join(parts[:-2]), " ".join(parts[-2:])
    return " ".join(parts[:-1]), parts[-1] if parts else ""


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def make_thumbnail(player_name: str, team_abbr: str, row: dict, out_path: str) -> str:
    color = _hex(TEAM_COLORS.get(team_abbr, DEFAULT_COLOR))
    img = _background(color)

    # Headshot, bottom-aligned, centered around x=900.
    shot = _fetch_headshot(row)
    if shot:
        new_h = 720
        new_w = int(shot.width * new_h / shot.height)
        shot = shot.resize((new_w, new_h), Image.LANCZOS)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        layer.paste(shot, (900 - new_w // 2, H - new_h))  # off-canvas parts are clipped
        img = Image.alpha_composite(img, layer)

    draw = ImageDraw.Draw(img, "RGBA")

    # Top-left: team pill + badge
    pill_font = _font(34)
    draw.rounded_rectangle((60, 45, 60 + 120, 45 + 56), 14, fill=color + (255,))
    tw = draw.textlength(team_abbr, font=pill_font)
    _text(draw, (60 + (120 - tw) / 2, 52), team_abbr, pill_font)
    _text(draw, (200, 54), badge_text(row), _font(38), fill=(255, 214, 10))

    # Name
    first, last = _split_name(player_name)
    _text(draw, (60, 125), first.upper(), _font(56), fill=(225, 225, 225), stroke=2)
    last_font = _fit_font(draw, last.upper(), 600, 150)
    _text(draw, (56, 175), last.upper(), last_font, stroke=4)

    # Stat tiles (2x2)
    tiles = pick_stats(row)
    tile_w, tile_h, gap = 280, 130, 20
    x0, y0 = 60, 365
    for i, (label, value) in enumerate(tiles):
        x = x0 + (i % 2) * (tile_w + gap)
        y = y0 + (i // 2) * (tile_h + gap)
        fill = color + (235,) if i == 0 else (0, 0, 0, 170)
        draw.rounded_rectangle((x, y, x + tile_w, y + tile_h), 20, fill=fill)
        _text(draw, (x + 24, y + 4), str(value), _font(92), stroke=2)
        _text(draw, (x + 26, y + 96), label, _font(28), fill=(235, 235, 235))

    footer = _footer(row)
    if footer:
        _text(draw, (62, 672), footer, _font(28), fill=(220, 220, 220), stroke=1)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    out = img.convert("RGB")
    out.save(out_path, quality=92) if out_path.lower().endswith((".jpg", ".jpeg")) else out.save(out_path)
    return out_path


def thumbnail_path(out_dir: str, date: str, player_name: str, team_abbr: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", player_name.lower()).strip("-")
    return os.path.join(out_dir, f"{date}_{slug}_{team_abbr}.jpg")
