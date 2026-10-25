"""Build the README's small animated product tour from reviewed screenshots."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
FRAMES = [
    ('Live queue', 'live.png'),
    ('Operational analytics', 'analytics.png'),
    ('Prediction performance', 'models.png'),
    ('Appointments', 'premium-appointments.png'),
    ('Mobile experience', 'mobile.png'),
]
FONT = ROOT / 'frontend/public/fonts/manrope-latin.woff2'


def main():
    # Pillow cannot decode WOFF2; use its built-in font so regeneration needs no extra tools.
    font = ImageFont.load_default()
    frames = []
    for title, filename in FRAMES:
        image = Image.open(ROOT / 'docs/screenshots' / filename).convert('RGB')
        image = ImageOps.contain(image, (700, 450), Image.Resampling.LANCZOS)
        canvas = Image.new('RGB', (720, 490), '#f2f6f4')
        canvas.paste(image, ((720 - image.width) // 2, 32 + (450 - image.height) // 2))
        ImageDraw.Draw(canvas).text((12, 10), title, fill='#173d3a', font=font)
        frames.append(canvas.convert('P', palette=Image.Palette.ADAPTIVE, colors=128))
    destination = ROOT / 'docs/demo/queuesense-tour.gif'
    frames[0].save(destination, save_all=True, append_images=frames[1:], duration=1450, loop=0, optimize=True, disposal=2)
    print(f'Wrote {destination.relative_to(ROOT)} ({destination.stat().st_size:,} bytes)')


if __name__ == '__main__':
    main()
