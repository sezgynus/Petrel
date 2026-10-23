"""Render the small Graphite interface and serial-port icons (Pillow only)."""
from pathlib import Path
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parents[3]
COLOR = '#529ec9'
# Coordinates use the shared 24-unit glyph inside an 18px square.
GLYPHS = {
    155: [[(3,7),(21,7)], [(17,3),(21,7),(17,11)],
          [(21,17),(3,17)], [(7,13),(3,17),(7,21)]],
    156: [[(8,2),(8,7)], [(16,2),(16,7)],
          [(5,7),(19,7),(19,12),(15,16),(9,16),(5,12),(5,7)],
          [(12,16),(12,22)]],
}

def main():
    for number, paths in GLYPHS.items():
        image = Image.new('RGB', (80,80), 'black')
        draw = ImageDraw.Draw(image)
        svg = []
        for path in paths:
            points = [((1+x*.75)*4,(1+y*.75)*4) for x,y in path]
            draw.line(points, fill=COLOR, width=6, joint='curve')
            for x,y in points:
                draw.ellipse((x-3,y-3,x+3,y+3), fill=COLOR)
            svg.append('<polyline points="' + ' '.join(f'{x},{y}' for x,y in path) + '"/>')
        source = ('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20">'
                  '<rect width="20" height="20" fill="#000000"/>'
                  '<g transform="translate(1,1) scale(.75)" fill="none" stroke="'+COLOR+'" '
                  'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">'
                  + ''.join(svg) + '</g></svg>\n')
        (ROOT / f'assets/icon-source/{number:03d}.svg').write_text(source, encoding='utf-8')
        image.resize((20,20), Image.Resampling.LANCZOS).save(
            ROOT / f'assets/icons/{number:03d}.jpg', 'JPEG',
            quality=94, subsampling=2, progressive=False, optimize=True)

if __name__ == '__main__':
    main()



