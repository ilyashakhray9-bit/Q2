from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

out = Path(__file__).resolve().parents[1] / 'examples'
out.mkdir(parents=True, exist_ok=True)
im = Image.new('RGB', (1400, 1400), '#F3F6F9')
d = ImageDraw.Draw(im)
regular = 'C:/Windows/Fonts/arial.ttf'
bold = 'C:/Windows/Fonts/arialbd.ttf'
def text(x, y, s, size=49, color='#132D40', heavy=False):
    d.text((x, y), s, font=ImageFont.truetype(bold if heavy else regular, size), fill=color)
d.rounded_rectangle((60, 60, 1340, 1340), 38, fill='white')
text(115, 110, 'НАБОР САЛФЕТОК', 68, heavy=True)
text(115, 205, 'Для кухни и сервировки', 36, '#557080')
# Schematic textile illustration, deliberately not a visual-count test.
for x, y in ((570, 320), (450, 380), (330, 440)):
    d.rounded_rectangle((x, y, x+510, y+270), 18, fill='#EEF0EE', outline='#BAC9CC', width=3)
    d.line((x+25,y+25,x+485,y+25,x+485,y+245), fill='#CDD6D5', width=3)
text(115, 790, 'Количество: 4 шт', 51, heavy=True)
text(115, 885, 'Размеры: 20 x 25 см', 51, heavy=True)
text(115, 980, 'Материал: хлопок', 51)
text(115, 1075, 'Цвет: белый', 51)
text(115, 1170, 'Вес: 250 г', 51)
im.save(out / 'card_with_errors.png')
Image.new('RGB', (600, 400), 'white').save(out / 'blank.png')
