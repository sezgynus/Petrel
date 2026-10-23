from PIL import Image, ImageDraw
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from lcd_resources import ICON_NFC_SHARE_FIRST
import math
O=Path(__file__).parent
B='#2c2e3c'; W='#edf3f7'; C='#42d5db'
mark=Image.open(O/'nfc-mark.png').convert('RGBA').resize((80,80),Image.Resampling.LANCZOS)
mask=mark.getchannel('A')
mark=Image.new('RGBA',mark.size,C); mark.putalpha(mask)
def frame(i):
 im=Image.new('RGB',(640,640),B); d=ImageDraw.Draw(im)
 def box(b,r,fill=None,outline=None,w=2): d.rounded_rectangle(tuple(int(v*4) for v in b),r*4,fill=fill,outline=outline,width=w*4)
 def line(p,c,w=2): d.line([(int(x*4),int(y*4)) for x,y in p],fill=c,width=w*4,joint='curve')
 if i<10: t=(1-math.cos(math.pi*i/9))/2
 elif i<17: t=1
 else: t=(1+math.cos(math.pi*(i-17)/6))/2
 # Portrait panel: screen centre is the NFC target.
 box((38,17,108,145),8,'#222c35','#71808e')
 box((45,25,101,121),4,'#1b252e','#455767',1)
 line([(51,33),(73,33)],'#71808e',2)
 line([(51,112),(88,112)],'#455767',2)
 d.ellipse((65*4,127*4,81*4,141*4),outline='#71808e',width=6)
 # Paired NFC arcs, centred on the reader rather than full radar rings.
 for k,r in enumerate((24,31,38)):
  color=C if t>.88 and (i-10)%7>=k+1 else '#304a55'
  bounds=((73-r)*4,(73-r)*4,(73+r)*4,(73+r)*4)
  d.arc(bounds,145,215,fill=color,width=7)
  d.arc(bounds,325,395,fill=color,width=7)
 # A small central target stays visible before the phone arrives.
 d.ellipse((70*4,70*4,76*4,76*4),fill=C)
 # Phone crosses in front of the panel and ends centred over the target.
 x=118-62*t; y=47-6*t
 if t<.65:
  line([(111,78),(100,78),(105,73)],C)
  line([(100,78),(105,83)],C)
 box((x,y,x+34,y+64),6,B,W,3)
 box((x+5,y+8,x+29,y+51),2,'#273741')
 line([(x+13,y+4),(x+21,y+4)],W,1)
 line([(x+13,y+57),(x+21,y+57)],W)
 im.paste(mark,(round((x+7)*4),round((y+18)*4)),mark)
 # Familiar enabled toggle below the NFC mark.
 box((x+11,y+42,x+24,y+48),3,C)
 d.ellipse(((x+18)*4,(y+43)*4,(x+22)*4,(y+47)*4),fill=B)
 return im.resize((160,160),Image.Resampling.LANCZOS)

if __name__ == '__main__':
 output=O.parent.parent/'icons'
 for i in range(12):
  frame(i*2).save(output/f'{ICON_NFC_SHARE_FIRST+i:03}.jpg',quality=94,subsampling=2,progressive=False)

