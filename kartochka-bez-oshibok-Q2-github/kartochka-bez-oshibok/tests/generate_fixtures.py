"""Synthetic regression images, NOT the user's unavailable product card.

Regenerate on Windows with Arial, or pass a local font using --font.
"""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", default="C:/Windows/Fonts/arialbd.ttf")
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[1] / "examples" / "regression"
    target.mkdir(parents=True, exist_ok=True)

    def font(size):
        return ImageFont.truetype(args.font, size)

    for name, value in [("count_22_stacked", 22), ("count_6_stacked", 6), ("count_122_stacked", 122), ("no_count", None)]:
        im = Image.new("RGB", (800, 1000), "#e5dee9")
        draw = ImageDraw.Draw(im)
        draw.text((40, 45), "НАБОР ДЛЯ ВОЛОС", font=font(46), fill="#3d2147")
        draw.text((40, 120), "ДЛИНА 14,5 СМ", font=font(25), fill="#3d2147")
        for n in range(7):
            x = 80 + n * 48
            draw.rounded_rectangle((x, 310 + n * 14, x + 30, 810 + n * 14), radius=14, fill="#85619a", outline="#593c68", width=3)
        draw.rounded_rectangle((500, 230, 745, 445), radius=45, fill="#492458")
        if value is not None:
            draw.text((622, 248), str(value), font=font(83), fill="white", anchor="mt")
            draw.text((622, 355), "штуки" if value != 6 else "штук", font=font(32), fill="white", anchor="mt")
        else:
            draw.text((622, 290), "НАБОР", font=font(35), fill="white", anchor="mt")
        draw.text((45, 930), "СИНТЕТИЧЕСКИЙ ТЕСТ", font=font(24), fill="#3d2147")
        im.save(target / f"{name}.png")

    for name, text in [("count_22_small", "22 штуки"), ("count_negated", "до 22 штук"), ("count_conflict", "6 штук     22 штуки")]:
        im = Image.new("RGB", (900, 900), "#ded1e3")
        draw = ImageDraw.Draw(im)
        draw.text((40, 40), "КАРТОЧКА ДЛЯ ТЕСТА", font=font(45), fill="#46264f")
        draw.rounded_rectangle((55, 220, 845, 650), radius=40, fill="#58336e")
        draw.text((100, 300), "НАДЁЖНЫЙ ЗАЖИМ", font=font(40), fill="white")
        draw.text((610 if name != "count_conflict" else 80, 600), text, font=font(20), fill="white")
        draw.text((45, 810), "СИНТЕТИЧЕСКИЙ ТЕСТ", font=font(25), fill="#46264f")
        im.save(target / f"{name}.png")


if __name__ == "__main__":
    main()
