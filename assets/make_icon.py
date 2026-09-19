"""Build-time helper: generates assets/app_icon.ico (a bold white "R" on a
solid colored circle) for DataRework.exe. Not needed at runtime -- only run
this when the icon needs regenerating.

Usage:
    python assets/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZES = [16, 32, 48, 256]
BG_COLOR = (0x1F, 0x6F, 0xEB)  # blue
FG_COLOR = (255, 255, 255)


def _find_font(size):
    candidates = [
        "arialbd.ttf",
        "Arial Bold.ttf",
        "DejaVuSans-Bold.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([0, 0, size - 1, size - 1], fill=BG_COLOR)

    font = _find_font(int(size * 0.62))
    text = "R"
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pos = ((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1])
    draw.text(pos, text, fill=FG_COLOR, font=font)
    return img


def main():
    out_dir = Path(__file__).resolve().parent
    out_path = out_dir / "app_icon.ico"
    images = [render(s) for s in SIZES]
    images[-1].save(
        out_path,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
    )
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
