"""Petrel-native Maintenance drawing; cached fields, fixed dashboard boundary.

No discovery, disk or network operations. Reuses the master menu font, icons,
header and thin cursor. Encoder focus changes paint only cursor strips.
"""
import textwrap
from graphite_theme import show_icon
from lcd_resources import ICON_LIBRARY_ID

BG=0x2125
INK=0xE75E
MUTED=0x9CD3
LINE=0x39C8
ACCENT=0x063B
WARNING=0xF56C


def _cached(v,key,signature):
    if v._maintenance_regions.get(key)==signature:
        return False
    v._maintenance_regions[key]=signature
    return True


def _text(v,key,value,x,y,cells=30,small=False,color=INK):
    v._maintenance_text(('native',key),value,x,y,cells,small,color=color,bg=BG)


def _cursor(v,key,y,height,selected):
    if _cached(v,('cursor',key),(y,height,selected)):
        v.lcd.draw_rectangle(1,ACCENT if selected else BG,4,y+5,7,y+height-6)


def _row(v,key,choice,index,y,height=48,icon=45):
    detail=bool(choice.detail)
    content=(choice.label,choice.detail,y,height,icon)
    if _cached(v,('row',key),content):
        v.lcd.draw_rectangle(1,BG,16,y,258,y+height-1)
        if icon is not None:
            show_icon(v.lcd,ICON_LIBRARY_ID,icon,26,y+15)
        x=60 if icon is not None else 24
        cells=(256-x)//8
        parts=textwrap.wrap(choice.label,cells)[:2] if height>=48 and not detail else (choice.label[:cells],)
        for line,part in enumerate(parts):
            v.lcd.draw_text(False,False,v.lcd.font8x16,INK,BG,x,y+(7 if detail or len(parts)>1 else 16)+line*18,part)
        if detail:
            v.lcd.draw_text(False,False,v.lcd.font6x12,MUTED,BG,x,y+28,choice.detail[:(256-x)//6])
        v.lcd.draw_line(LINE,16,y+height-1,256,y+height-1)
    _cursor(v,key,y,height,index==v._maintenance_selection)


def _scroll(v,start,total,visible,y=90,height=253):
    if _cached(v,'scrollbar',(start,total,visible,y,height)):
        v.lcd.draw_rectangle(1,BG,264,84,268,355)
        if total>visible:
            h=max(10,height*visible//total)
            top=y+(height-h)*start//(total-visible)
            v.lcd.draw_rectangle(1,LINE,265,y,267,y+height-1)
            v.lcd.draw_rectangle(1,ACCENT,265,top,267,top+h-1)


def _bar(v,key,item,x,y,width):
    fill=None if item.progress is None else int(width*item.progress)
    if _cached(v,('bar',key),(fill,item.state,x,y,width)):
        v.lcd.draw_rectangle(1,LINE,x,y,x+width-1,y+3)
        if fill:
            v.lcd.draw_rectangle(1,WARNING if item.state=='due' else ACCENT,x,y,x+fill-1,y+3)


def _home(v,screen):
    choices=screen.choices
    _row(v,'back',choices[0],0,31,52,13)
    _cursor(v,'care',88,112,v._maintenance_selection==1)
    _text(v,'care_label','Care schedule',24,92,28)
    _text(v,'care_summary',screen.heading,24,114,39,True,
          WARNING if v._maintenance_storage_errors() or v._maintenance_records_failed else MUTED)
    items=screen.care
    for i in range(2):
        y=137+i*32
        if i<len(items):
            item=items[i]
            _text(v,('care_name',i),item.label,24,y,24,True)
            _text(v,('care_status',i),item.detail,174,y,13,True,WARNING if item.state=='due' else MUTED)
            _bar(v,('home',i),item,24,y+17,232)
        else:
            _text(v,('care_name',i),'Select to set up' if i==0 else '',24,y,38,True,MUTED)
            _text(v,('care_status',i),'',174,y,13,True)
            if _cached(v,('bar',('home',i)),('empty',y)):
                v.lcd.draw_rectangle(1,BG,24,y+17,256,y+20)
    for index,y,icon in ((2,204,218),(3,256,45),(4,308,45)):
        _row(v,('root',index),choices[index],index,y,48,icon)


def _list(v,screen):
    choices=screen.choices
    _row(v,'back',choices[0],0,31,52,13)
    count=len(choices)-1
    care=screen.kind=='care'
    visible=3 if care else 5
    selection=v._maintenance_selection
    start=getattr(v,'_maintenance_scroll',0)
    if selection>0:
        start=max(0,min(start,selection-1),selection-visible)
    start=min(start,max(0,count-visible))
    if start!=getattr(v,'_maintenance_scroll',0):
        v.lcd.draw_rectangle(1,BG,0,84,271,359)
        v._maintenance_regions={k:value for k,value in v._maintenance_regions.items()
            if k in (('row','back'),('cursor','back'))}
    v._maintenance_scroll=start
    items={(item.policy.task_id,item.policy.device):item for item in screen.care}
    height=82 if care else 52
    for slot in range(visible):
        index=start+slot+1
        y=86+slot*height
        if index>=len(choices):
            if _cached(v,('empty',slot),(index,count)):
                v.lcd.draw_rectangle(1,BG,0,y,260,min(359,y+height-1))
            continue
        choice=choices[index]
        if care and choice.action=='service_task':
            policy=choice.value[0]
            item=items.get((policy.task_id,policy.device))
            if item is not None:
                key=('care_row',slot)
                label=textwrap.wrap(item.label,28)[:2]
                sig=(tuple(label),item.detail,y)
                if _cached(v,key,sig):
                    v.lcd.draw_rectangle(1,BG,16,y,259,y+height-1)
                    for line,value in enumerate(label):
                        v.lcd.draw_text(False,False,v.lcd.font8x16,INK,BG,24,y+4+line*18,value)
                    v.lcd.draw_text(False,False,v.lcd.font6x12,WARNING if item.state=='due' else MUTED,
                        BG,24,y+43,item.detail)
                    v.lcd.draw_line(LINE,16,y+height-1,256,y+height-1)
                    # Clearing the row also clears its old track.
                    v._maintenance_regions.pop(('bar',slot),None)
                _bar(v,slot,item,24,y+64,232)
                _cursor(v,key,y,height-2,selection==index)
                continue
        _row(v,('list',slot),choice,index,y,height,None if choice.action=='none' else 45)
    _scroll(v,start,count,visible)


def _detail(v,screen):
    choices=screen.choices
    pinned=bool(choices and choices[0].action in ('back','home','result_back'))
    if pinned:
        _row(v,'back',choices[0],0,31,52,13)
    top=93 if pinned else 45
    for i,part in enumerate((textwrap.wrap(screen.heading,30)+['',''])[:2]):
        _text(v,('heading',i),part,12,top+i*18,31,
              color=WARNING if screen.tone in ('attention','danger') else INK)
    lines=[line for value in screen.lines for line in (textwrap.wrap(str(value),39) or [''])]
    if v._maintenance_notice:
        lines=textwrap.wrap(v._maintenance_notice.replace('_',' '),39)[:2]+lines
    visible_lines=5 if pinned else 7
    for i in range(visible_lines):
        _text(v,('line',i),lines[i] if i<len(lines) else '',12,top+41+i*18,40,True,MUTED)
    first=1 if pinned else 0
    total=len(choices)-first
    visible=3
    selected=max(0,v._maintenance_selection-first)
    start=max(0,min(getattr(v,'_maintenance_scroll',0),selected),selected-visible+1)
    start=min(start,max(0,total-visible))
    if start!=getattr(v,'_maintenance_scroll',0):
        v.lcd.draw_rectangle(1,BG,0,239,271,359)
        v._maintenance_regions={k:value for k,value in v._maintenance_regions.items()
            if not (isinstance(k,tuple) and len(k)>1 and isinstance(k[1],tuple) and k[1][0]=='action')}
    v._maintenance_scroll=start
    for slot in range(visible):
        index=first+start+slot
        if index<len(choices):
            _row(v,('action',slot),choices[index],index,241+slot*39,35,None)
    if total>visible:
        _text(v,'action_count','%d/%d'%(selected+1,total),216,220,8,True,MUTED)
    owner=getattr(v.pd,'maintenance_pulse',None)
    color=getattr(owner,'display_color',None) if v._maintenance_page=='pulse' else None
    previous=v._maintenance_regions.get('color_patch')
    if (color is not None or previous is not None) and _cached(v,'color_patch',color):
        v.lcd.draw_rectangle(1,color if color is not None else BG,16,206,255,226)


def draw_maintenance(v,screen):
    v._maintenance_selection=max(0,min(v._maintenance_selection,max(0,len(screen.choices)-1)))
    frame=(id(v.lcd),v._maintenance_page,screen.kind,screen.title,len(screen.choices))
    if frame!=v._maintenance_frame:
        v._maintenance_frame=frame
        v._maintenance_regions={}
        v._maintenance_scroll=0
        v._list_render=None
        v.lcd.draw_rectangle(1,BG,0,0,271,359)
        v._header_clock_drawn=None
        v.Draw_Title(screen.title)
    v._maintenance_drawn_choices=tuple((c.action,c.value) for c in screen.choices)
    if screen.kind=='home':
        _home(v,screen)
    elif screen.kind in ('list','care') and screen.choices:
        _list(v,screen)
    else:
        _detail(v,screen)
