"""Render approved DWIN device settings tiles, retaining Graphite IDs 56/57."""
from pathlib import Path
import math
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parents[3]
S=8
blue='#429bd4'
def tile(selected):
 bg='#183e4c' if selected else '#292e35'
 im=Image.new('RGB',(110*S,100*S),'black');d=ImageDraw.Draw(im)
 def rect(box,radius,fill=None,outline=None,width=1):
  d.rounded_rectangle(tuple(v*S for v in box),radius=radius*S,fill=fill,outline=outline,width=round(width*S))
 def circle(cx,cy,rad,fill=None,outline=None,width=1):
  d.ellipse(tuple(v*S for v in (cx-rad,cy-rad,cx+rad,cy+rad)),fill=fill,outline=outline,width=round(width*S))
 rect((1,1,109,99),16,bg,'#00c4dc' if selected else '#3c454f')
 # Dimensions follow the docs bezel: width/height=.55, screen in upper
 # section, centered knob below; top and bottom corners are chamfered.
 housing=[(46,14),(64,14),(69,18),(69,60),(65,63),(45,63),(41,60),(41,18)]
 points=[(x*S,y*S) for x,y in housing]
 d.polygon(points,fill=bg)
 d.line(points+[points[0]],fill=blue,width=round(3*S),joint='curve')
 rect((46.2,19.5,63.8,48.5),1.2,blue)
 circle(55,57,3.8,bg,blue,2.5)
 # A separate gear badge leaves the centered encoder fully visible.
 circle(41,53,10.6,bg)
 pts=[]
 for i in range(8):
  for off,rad in [(-.46,6.6),(-.27,9.1),(.27,9.1),(.46,6.6)]:
   a=(i+off)*math.tau/8
   pts.append(((41+math.cos(a)*rad)*S,(53+math.sin(a)*rad)*S))
 d.line(pts+[pts[0]],fill=blue,width=round(2.5*S),joint='curve')
 circle(41,53,2.8,bg,blue,2.2)
 return im.resize((110,100),Image.Resampling.LANCZOS)


def svg(selected):
    bg = '#183e4c' if selected else '#292e35'
    border = '#00c4dc' if selected else '#3c454f'
    points = []
    for i in range(8):
        for off, rad in [(-.46,6.6),(-.27,9.1),(.27,9.1),(.46,6.6)]:
            angle = (i+off)*math.tau/8
            points.append(f'{41+math.cos(angle)*rad:.4f},{53+math.sin(angle)*rad:.4f}')
    gear = ' '.join(points + points[:1])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="110" height="100" viewBox="0 0 110 100">
<rect width="110" height="100" fill="#000000"/>
<rect x="1" y="1" width="108" height="98" rx="16" fill="{bg}" stroke="{border}"/>
<g stroke="{blue}" stroke-linejoin="round" stroke-linecap="round">
<path d="M46 14H64L69 18V60L65 63H45L41 60V18Z" fill="{bg}" stroke-width="3"/>
<rect x="46.2" y="19.5" width="17.6" height="29" rx="1.2" fill="{blue}" stroke="none"/>
<circle cx="55" cy="57" r="3.8" fill="{bg}" stroke-width="2.5"/>
<circle cx="41" cy="53" r="10.6" fill="{bg}" stroke="none"/>
<polyline points="{gear}" fill="none" stroke-width="2.5"/>
<circle cx="41" cy="53" r="2.8" fill="{bg}" stroke-width="2.2"/>
</g></svg>\n'''


def main():
    for icon_id, selected in ((56, False), (57, True)):
        (ROOT/f'assets/icon-source/{icon_id:03d}.svg').write_text(svg(selected))
        tile(selected).save(ROOT/f'assets/icons/{icon_id:03d}.jpg', 'JPEG',
                            quality=94, subsampling=2, progressive=False)


if __name__ == '__main__':
    main()
