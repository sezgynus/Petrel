"""Render 20px Graphite RFID action glyphs and editable SVG sources."""
from pathlib import Path
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parents[3]
COLOR = '#529ec9'
GLYPHS = {
 27: ([[(7,2),(17,2),(22,7),(22,17),(17,22),(7,22),(2,17),(2,7),(7,2)], [(12,7),(12,13)]], [(12,17,.6)]),
 36: ([[(12,3),(12,8)],[(4,16),(9,14)],[(20,16),(15,14)],[(19,18),(22,22)]],[(12,12,9),(12,12,3)]),
 37: ([[(3,3),(13,3),(22,12),(12,22),(3,13),(3,3)],[(11,13),(17,13)],[(14,10),(14,16)]],[(7,7,1)]),
 38: ([[(3,6),(21,6)],[(9,6),(9,3),(15,3),(15,6)],[(5,6),(6,21),(18,21),(19,6)],[(10,10),(10,17)],[(14,10),(14,17)]],[]),
 39: ([[(3,12),(21,12)],[(14,5),(21,12),(14,19)]],[]),
 40: ([[(3,9),(7,5),(13,3),(19,6),(21,12),(19,18),(13,21),(7,19)],[(3,3),(3,9),(9,9)]],[]),
}
def main():
 for number,(paths,circles) in GLYPHS.items():
  im=Image.new('RGB',(80,80),'black');d=ImageDraw.Draw(im);svg=[]
  def pt(x):return (1+x*.75)*4
  for line in paths:
   points=[(pt(x),pt(y)) for x,y in line];d.line(points,fill=COLOR,width=6,joint='curve')
   for x,y in points:d.ellipse((x-3,y-3,x+3,y+3),fill=COLOR)
   svg.append('<polyline points="'+' '.join(f'{x},{y}' for x,y in line)+'"/>')
  for x,y,rad in circles:
   box=(pt(x-rad),pt(y-rad),pt(x+rad),pt(y+rad));d.ellipse(box,outline=COLOR,width=6)
   svg.append(f'<circle cx="{x}" cy="{y}" r="{rad}"/>')
  source=('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20">'
    '<rect width="20" height="20" fill="#000000"/><g transform="translate(1,1) scale(.75)" '
    f'fill="none" stroke="{COLOR}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">'
    +''.join(svg)+'</g></svg>\n')
  (ROOT/f'assets/icon-source/{number:03d}.svg').write_text(source,encoding='utf-8')
  im.resize((20,20),Image.Resampling.LANCZOS).save(ROOT/f'assets/icons/{number:03d}.jpg',
    'JPEG',quality=94,subsampling=2,progressive=False,optimize=True)
if __name__=='__main__':main()

