"""Team logo as thumbnail background art.

The NBA serves logos as SVG (cdn.nba.com/logos/nba/{team_id}/primary/L/logo.svg),
which Pillow can't read. Instead the logo is rendered by the Selenium Chrome
session you already have open, then turned into a transparent image.

Usage (while the driver is still open):
    attach_logo(driver, stat_row, team_abbr)     # stores row["LOGO_BYTES"]
Then in make_thumbnail():
    layer = logo_layer(row, W, H)                # RGBA layer, or None
"""
import io
from urllib.parse import quote

from PIL import Image, ImageChops

LOGO_OPACITY = 0.35   # 0 = invisible, 1 = fully opaque
LOGO_SIZE = 720       # logo height in px on the 1280x720 canvas
LOGO_CENTER_X = 340   # left side (the headshot stays centered near x=900)

# NBA team IDs, keyed by lowercase abbreviation (what abbr_for() returns).
TEAM_IDS = {
    "atl": 1610612737, "bos": 1610612738, "cle": 1610612739, "nop": 1610612740,
    "chi": 1610612741, "dal": 1610612742, "den": 1610612743, "gsw": 1610612744,
    "hou": 1610612745, "lac": 1610612746, "lal": 1610612747, "mia": 1610612748,
    "mil": 1610612749, "min": 1610612750, "bkn": 1610612751, "nyk": 1610612752,
    "orl": 1610612753, "ind": 1610612754, "phi": 1610612755, "phx": 1610612756,
    "por": 1610612757, "sac": 1610612758, "sas": 1610612759, "okc": 1610612760,
    "tor": 1610612761, "uta": 1610612762, "mem": 1610612763, "was": 1610612764,
    "det": 1610612765, "cha": 1610612766,
}

_CACHE: dict[str, bytes] = {}


def logo_url(team_abbr: str) -> str:
    tid = TEAM_IDS.get(team_abbr.lower())
    return f"https://cdn.nba.com/logos/nba/{tid}/primary/L/logo.svg" if tid else ""


def _matte(on_black_png: bytes, on_white_png: bytes) -> Image.Image:
    """Recover a transparent RGBA image from two screenshots of the same
    graphic, one on a black page and one on a white page. A pixel with
    opacity a differs between the two by (1 - a) * 255, so alpha falls out
    of the difference. Works whether or not Chrome can capture transparency."""
    black = Image.open(io.BytesIO(on_black_png)).convert("RGB")
    white = Image.open(io.BytesIO(on_white_png)).convert("RGB")
    r, g, b = ImageChops.subtract(white, black).split()
    diff = ImageChops.lighter(ImageChops.lighter(r, g), b)
    rgba = black.copy()  # color over black ~ color * alpha; fine for a watermark
    rgba.putalpha(ImageChops.invert(diff))
    return rgba


def fetch_team_logo(driver, team_abbr: str, px: int = 720) -> bytes | None:
    """Render the SVG in a temporary tab and return a transparent PNG (bytes).
    The main tab (the box-score page used for headshot downloads) is untouched."""
    url = logo_url(team_abbr)
    if not url:
        print(f"    ! no team id for '{team_abbr}', skipping logo")
        return None

    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    original = driver.current_window_handle
    try:
        driver.switch_to.new_window("tab")
        shots = []
        for bg in ("#000", "#fff"):
            html = (
                f'<body style="margin:0;background:{bg}">'
                f'<img id="l" src="{url}" style="display:block;width:{px}px;'
                f'height:{px}px;object-fit:contain"></body>'
            )
            driver.get("data:text/html;charset=utf-8," + quote(html))
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script(
                    "const i = document.getElementById('l');"
                    "return i.complete && i.naturalWidth > 0;"
                )
            )
            shots.append(driver.find_element(By.ID, "l").screenshot_as_png)

        out = io.BytesIO()
        _matte(shots[0], shots[1]).save(out, "PNG")
        return out.getvalue()
    except Exception as e:
        print(f"    ! logo render failed for {team_abbr} ({e.__class__.__name__})")
        return None
    finally:
        try:
            driver.close()  # the temporary tab only
        except Exception:
            pass
        driver.switch_to.window(original)


def attach_logo(driver, row: dict, team_abbr: str) -> None:
    """Render the logo once per team per run and stash the bytes on the row."""
    key = team_abbr.lower()
    if key not in _CACHE:
        data = fetch_team_logo(driver, key)
        if data:
            _CACHE[key] = data
    if key in _CACHE:
        row["LOGO_BYTES"] = _CACHE[key]


def logo_layer(row: dict, width: int, height: int) -> Image.Image | None:
    """Full-canvas RGBA layer with the faded logo, or None if unavailable."""
    data = row.get("LOGO_BYTES")
    if not data:
        return None
    try:
        logo = Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:
        return None
    w = int(logo.width * LOGO_SIZE / logo.height)
    logo = logo.resize((w, LOGO_SIZE), Image.LANCZOS)
    logo.putalpha(logo.getchannel("A").point(lambda a: int(a * LOGO_OPACITY)))
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    layer.paste(logo, (LOGO_CENTER_X - w // 2, (height - LOGO_SIZE) // 2))
    return layer
