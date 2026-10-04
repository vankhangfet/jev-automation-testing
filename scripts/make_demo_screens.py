"""Generate the demo login screenshots for `demo/screens/login/`.

Each screen is a simple synthetic mobile login mock-up. One is correct; the
rest carry one planted defect each so the demo rules in
`demo/rules/login.yaml` have something real to catch.

Run:  uv run python scripts/make_demo_screens.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 360, 760
OUT = Path(__file__).resolve().parents[1] / "demo" / "screens" / "login"

BG = (249, 250, 252)
INK = (31, 41, 55)
MUTED = (107, 114, 128)
BLUE = (37, 99, 235)
RED = (220, 38, 38)
FIELD_BG = (255, 255, 255)
FIELD_BORDER = (209, 213, 219)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def base() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)


def field(d: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int,
          label: str) -> None:
    d.rounded_rectangle((x0, y0, x1, y1), radius=10, fill=FIELD_BG,
                        outline=FIELD_BORDER, width=2)
    d.text((x0 + 14, y0 + (y1 - y0 - 18) // 2), label, font=_font(16), fill=MUTED)


def button(d: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int,
           label: str) -> None:
    d.rounded_rectangle((x0, y0, x1, y1), radius=10, fill=BLUE)
    w = d.textlength(label, font=_font(18, bold=True))
    d.text((x0 + (x1 - x0 - w) / 2, y0 + (y1 - y0 - 22) // 2), label,
           font=_font(18, bold=True), fill=(255, 255, 255))


def login_ok() -> None:
    img, d = base()
    d.text((30, 90), "Welcome back", font=_font(28, bold=True), fill=INK)
    d.text((30, 132), "Sign in to continue", font=_font(15), fill=MUTED)
    field(d, 30, 250, 330, 310, "Email")
    field(d, 30, 330, 330, 390, "Password")
    button(d, 30, 450, 330, 510, "Sign in")
    d.text((30, 545), "Forgot password?", font=_font(14), fill=BLUE)
    img.save(OUT / "01_login_ok.png")


def login_layout_broken() -> None:
    """Title overlaps the email field; button hangs off the right edge."""
    img, d = base()
    d.text((30, 268), "Welcome back", font=_font(28, bold=True), fill=INK)
    field(d, 30, 250, 330, 310, "Email")          # title sits on top of it
    field(d, 30, 330, 330, 390, "Password")
    button(d, 140, 450, 420, 510, "Sign in")      # x1 > W: half off-screen
    d.text((30, 545), "Forgot password?", font=_font(14), fill=BLUE)
    img.save(OUT / "02_login_layout_broken.png")


def login_i18n_key() -> None:
    """Raw i18n keys rendered instead of human text."""
    img, d = base()
    d.text((30, 90), "login.title", font=_font(28, bold=True), fill=INK)
    d.text((30, 132), "auth.subtitle.hint", font=_font(15), fill=MUTED)
    field(d, 30, 250, 330, 310, "Email")
    field(d, 30, 330, 330, 390, "Password")
    button(d, 30, 450, 330, 510, "Sign in")
    d.text((30, 545), "Forgot password?", font=_font(14), fill=BLUE)
    img.save(OUT / "03_login_i18n_keys.png")


def login_error_banner() -> None:
    """Red error banner covering the top of the form area."""
    img, d = base()
    d.text((30, 90), "Welcome back", font=_font(28, bold=True), fill=INK)
    d.text((30, 132), "Sign in to continue", font=_font(15), fill=MUTED)
    d.rectangle((0, 185, W, 245), fill=RED)
    w = d.textlength("Oops! Something went wrong.", font=_font(15, bold=True))
    d.text(((W - w) / 2, 205), "Oops! Something went wrong.",
           font=_font(15, bold=True), fill=(255, 255, 255))
    field(d, 30, 250, 330, 310, "Email")          # starts right under the banner
    field(d, 30, 330, 330, 390, "Password")
    button(d, 30, 450, 330, 510, "Sign in")
    d.text((30, 545), "Forgot password?", font=_font(14), fill=BLUE)
    img.save(OUT / "04_login_error_banner.png")


def login_blank() -> None:
    """Almost-empty screen with only a small loading dot."""
    img, d = base()
    d.ellipse((W // 2 - 8, H // 2 - 8, W // 2 + 8, H // 2 + 8),
              outline=MUTED, width=3)
    img.save(OUT / "05_login_blank.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    login_ok()
    login_layout_broken()
    login_i18n_key()
    login_error_banner()
    login_blank()
    print(f"Generated {len(list(OUT.glob('*.png')))} screens in {OUT}")


if __name__ == "__main__":
    main()
