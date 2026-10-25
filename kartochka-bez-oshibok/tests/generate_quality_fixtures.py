"""Deterministic artificial product layouts; no real photos or AI images."""
import json
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parents[1] / 'examples' / 'quality'
CASES = [
    ('match_clear', '6 штук', 42, False, 'match'),
    ('wrong_clear', '22 штуки', 42, False, 'different'),
    ('match_small', '6 штук', 14, False, 'match'),
    ('wrong_small', '22 штуки', 14, False, 'different'),
    ('match_busy', '6 штук', 42, True, 'match'),
    ('wrong_busy', '22 штуки', 42, True, 'different'),
    ('missing_busy', '', 42, True, 'missing'),
    ('dimensions_only', 'ДЛИНА 22 СМ', 30, False, 'missing'),
    ('price_only', 'Цена за 6 шт', 32, False, 'review'),
    ('gift_only', '6 шт в подарок', 32, False, 'review'),
    ('negated_label', 'Не количество: 6 шт', 30, False, 'review'),
    ('range', 'от 6 до 22 штук', 30, False, 'review'),
    ('conflict', '6 штук      22 штуки', 30, False, 'review'),
    ('wrong_tiny', '22 штуки', 6, False, 'different'),
    ('wrong_low_contrast', '22 штуки', 14, False, 'different'),
]


def main():
    BASE.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, text, size, busy, truth in CASES:
        im = Image.new('RGB', (760, 760), '#ece4ee')
        d = ImageDraw.Draw(im)
        font = lambda n: ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', n)
        d.text((30, 30), 'АКСЕССУАРЫ ДЛЯ ВОЛОС', font=font(33), fill='#38243d')
        d.text((30, 90), 'УДОБНО БРАТЬ С СОБОЙ', font=font(20), fill='#38243d')
        for i in range(6):
            d.rounded_rectangle((55+i*80, 180+i*13, 90+i*80, 490+i*13), 15, fill='#ae74bb')
        d.rectangle((20, 590, 740, 695), fill='#4b3455')
        if busy:
            rng = random.Random(20261025)
            for _ in range(150):
                x, y = rng.randint(20, 740), rng.randint(590, 695)
                d.line((x, y, x+45, y+20), fill=rng.choice(['#72567d', '#90739a', '#36213f']), width=3)
        color = '#5b445f' if name == 'wrong_low_contrast' else 'white'
        d.text((55, 625), text, font=font(size), fill=color)
        d.text((30, 720), 'ИСКУССТВЕННЫЙ ТЕСТ • НЕ ФОТО ТОВАРА', font=font(18), fill='#38243d')
        im.save(BASE / (name+'.png'))
        manifest.append(dict(id=name, file=name+'.png', origin='synthetic', inscription=text,
                             font_px=size, truth=truth, expected=6,
                             challenge=name in ('wrong_tiny', 'wrong_low_contrast')))
    (BASE/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
