"""Petrel-native Maintenance drawing; cached fields, fixed dashboard boundary.

No discovery, disk or network operations. Reuses the master menu font, icons,
header and thin cursor. Encoder focus changes paint only cursor strips.
"""
import textwrap
from graphite_theme import show_icon, draw_scrollbar
from lcd_resources import ICON_LIBRARY_ID, ICON_MAINTENANCE_CARE
from petrel.features.maintenance.ui.icons import icon_for

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


def _row(v,key,choice,index,y,height=48,icon=None):
    detail=bool(choice.detail)
    x=60 if icon is not None else 24
    cells=(256-x)//8
    parts=textwrap.wrap(choice.label,cells)[:2] if height>=48 and not detail else (choice.label[:cells],)
    shape=(y,height,icon is not None,detail,len(parts))
    if _cached(v,('row',key),shape):
        _forget(v,key,keep=('row',))
        v.lcd.draw_rectangle(1,BG,16,y,259,y+height-1)
        v.lcd.draw_line(LINE,16,y+height-1,256,y+height-1)
    if icon is not None and _cached(v,('icon',key),(icon,26,y+(height-20)//2)):
        top=y+(height-20)//2
        v.lcd.draw_rectangle(1,BG,26,top,49,top+23)
        show_icon(v.lcd,ICON_LIBRARY_ID,icon,26,top)
    for line,value in enumerate(parts):
        _text(v,('label',key,line),value,x,y+(3 if detail and height<48 else 7 if detail or len(parts)>1 else 16 if height>=48 else 9)+line*18,cells)
    if detail:
        _text(v,('detail',key),choice.detail,x,y+(21 if height<48 else 28),(256-x)//6,True,MUTED)
    _cursor(v,key,y,height,index==v._maintenance_selection)


def _contains(key,token):
    return key==token or isinstance(key,tuple) and any(_contains(part,token) for part in key)


def _forget(v,token,keep=()):
    for key in tuple(v._maintenance_regions):
        if _contains(key,token) and not (isinstance(key,tuple) and key[0] in keep):
            del v._maintenance_regions[key]


def _move_viewport(v,prefix,old_start,start,visible,height,top,first=1):
    delta=start-old_start
    if not delta: return
    # Same panel operation as master _draw_list_menu, restricted to this viewport.
    # Remove the old cursor before its pixels are copied to the next row.
    bottom=top+visible*height-1
    v.lcd.draw_rectangle(1,BG,4,top,7,bottom)
    if abs(delta)<visible:
        v.lcd.move_area(1,v.DWIN_SCROLL_UP if delta>0 else v.DWIN_SCROLL_DOWN,
            abs(delta)*height,BG,0,top,259,bottom)
    else:
        v.lcd.draw_rectangle(1,BG,0,top,259,bottom)
    retained=set(range(max(old_start,start)+first,min(old_start+visible,start+visible)+first)) if abs(delta)<visible else set()
    tokens={key[1] for key in v._maintenance_regions if isinstance(key,tuple) and len(key)>1
            and key[0] in ('row','cursor','care_row') and isinstance(key[1],tuple) and key[1][0]==prefix}
    for token in tokens:
        if token[1] not in retained:
            _forget(v,token)
            continue
        for key,value in tuple(v._maintenance_regions.items()):
            if not _contains(key,token): continue
            kind=key[0]
            value=list(value)
            if kind in ('row','cursor','care_row'):
                value[0]-=delta*height
                if kind=='cursor': value[2]=False
            elif kind=='native': value[2]-=delta*height
            elif kind=='icon': value[2]-=delta*height
            elif kind=='bar': value[3]-=delta*height
            v._maintenance_regions[key]=tuple(value)
    # Empty-slot sentinels belong to physical rows, not logical entries.
    for key in tuple(v._maintenance_regions):
        if isinstance(key,tuple) and key[0]=='empty': del v._maintenance_regions[key]


def _scroll(v,start,total,visible,y=90,height=253):
    if _cached(v,'scrollbar',(start,total,visible,y,height)):
        draw_scrollbar(v.lcd,start,total,visible,y,height)

def _bar(v,key,item,x,y,width):
    fill=None if item.progress is None else int(width*item.progress)
    signature=(fill,item.state,x,y,width)
    old=v._maintenance_regions.get(('bar',key))
    if old==signature: return
    v._maintenance_regions[('bar',key)]=signature
    color=WARNING if item.state=='due' else ACCENT
    if old is None or old[2:]!=(x,y,width) or old[0] is None or fill is None:
        v.lcd.draw_rectangle(1,LINE,x,y,x+width-1,y+3)
        if fill: v.lcd.draw_rectangle(1,color,x,y,x+fill-1,y+3)
    elif old[1]!=item.state:
        if fill: v.lcd.draw_rectangle(1,color,x,y,x+fill-1,y+3)
        if fill<old[0]: v.lcd.draw_rectangle(1,LINE,x+fill,y,x+old[0]-1,y+3)
    elif fill>old[0]:
        v.lcd.draw_rectangle(1,color,x+old[0],y,x+fill-1,y+3)
    elif fill<old[0]:
        v.lcd.draw_rectangle(1,LINE,x+fill,y,x+old[0]-1,y+3)


def _home(v,screen):
    choices=screen.choices
    v._draw_header_back(v._maintenance_selection == 0)
    _cursor(v,'care',36,112,v._maintenance_selection==1)
    if _cached(v,'care_icon',ICON_MAINTENANCE_CARE):
        show_icon(v.lcd,ICON_LIBRARY_ID,ICON_MAINTENANCE_CARE,24,39)
    _text(v,'care_label','Care schedule',50,40,25)
    _text(v,'care_summary',screen.heading,24,62,39,True,
          WARNING if v._maintenance_storage_errors() or v._maintenance_records_failed else MUTED)
    items=screen.care
    for i in range(2):
        y=85+i*32
        if i<len(items):
            item=items[i]
            _text(v,('care_name',i),item.label,24,y,24,True)
            brief=(item.detail.split(' ',1)[0]
                   if item.policy.basis!='calendar_s' and item.progress is not None
                   and item.state!='due' else item.detail)
            _text(v,('care_status',i),brief,174,y,13,True,
                  WARNING if item.state=='due' else MUTED)
            _bar(v,('home',i),item,24,y+17,232)
        else:
            _text(v,('care_name',i),'Select to set up' if i==0 else '',24,y,38,True,MUTED)
            _text(v,('care_status',i),'',174,y,13,True)
            if _cached(v,('bar',('home',i)),('empty',y)):
                v.lcd.draw_rectangle(1,BG,24,y+17,256,y+20)
    for index,y in ((2,152),(3,204),(4,256)):
        _row(v,('root',index),choices[index],index,y,48,icon_for(choices[index]))


def _list(v,screen):
    choices=screen.choices
    v._draw_header_back(v._maintenance_selection == 0)
    count=len(choices)-1
    care=screen.kind=='care'
    visible=4 if care else 6
    height=80 if care else 52
    selection=v._maintenance_selection
    old_start=getattr(v,'_maintenance_scroll',0)
    start=old_start
    if selection>0:
        start=max(0,min(start,selection-1),selection-visible)
    start=min(start,max(0,count-visible))
    _move_viewport(v,'entry',old_start,start,visible,height,34)
    v._maintenance_scroll=start
    items={(item.policy.task_id,item.policy.device):item for item in screen.care}
    for slot in range(visible):
        index=start+slot+1
        y=34+slot*height
        key=('entry',index)
        if index>=len(choices):
            if _cached(v,('empty',slot),(index,count)):
                v.lcd.draw_rectangle(1,BG,0,y,260,min(359,y+height-1))
                _forget(v,key)
            continue
        v._maintenance_regions.pop(('empty',slot),None)
        choice=choices[index]
        if care and choice.action=='service_task':
            policy=choice.value[0]
            item=items.get((policy.task_id,policy.device))
            if item is not None:
                if _cached(v,('care_row',key),(y,height)):
                    _forget(v,key,keep=('care_row',))
                    v.lcd.draw_rectangle(1,BG,16,y,259,y+height-1)
                    v.lcd.draw_line(LINE,16,y+height-1,256,y+height-1)
                icon=icon_for(choice)
                if icon is not None and _cached(v,('icon',key),(icon,26,y+7)):
                    v.lcd.draw_rectangle(1,BG,26,y+7,49,y+30)
                    show_icon(v.lcd,ICON_LIBRARY_ID,icon,26,y+7)
                parts=textwrap.wrap(item.label,24)[:2]
                for line in range(2):
                    _text(v,('care_label',key,line),parts[line] if line<len(parts) else '',60,y+4+line*18,24)
                _text(v,('care_detail',key),item.detail,24,y+43,38,True,
                    WARNING if item.state=='due' else MUTED)
                _bar(v,key,item,24,y+64,232)
                _cursor(v,key,y,height-2,selection==index)
                continue
        _row(v,key,choice,index,y,height,icon_for(choice))
    _scroll(v,start,count,visible,34,visible*height)


def _detail(v,screen):
    choices=screen.choices
    pinned=bool(choices and choices[0].action in ('back','home','result_back'))
    if pinned:
        v._draw_header_back(v._maintenance_selection == 0)
    top=45
    for i,part in enumerate((textwrap.wrap(screen.heading,30)+['',''])[:2]):
        _text(v,('heading',i),part,12,top+i*18,31,
              color=WARNING if screen.tone in ('attention','danger') else INK)
    lines=[line for value in screen.lines for line in (textwrap.wrap(str(value),39) or [''])]
    if v._maintenance_notice:
        lines=textwrap.wrap(v._maintenance_notice.replace('_',' '),39)[:2]+lines
    visible_lines=7
    for i in range(visible_lines):
        _text(v,('line',i),lines[i] if i<len(lines) else '',12,top+41+i*18,40,True,MUTED)
    first=1 if pinned else 0
    total=len(choices)-first
    visible=3
    selected=max(0,v._maintenance_selection-first)
    start=max(0,min(getattr(v,'_maintenance_scroll',0),selected),selected-visible+1)
    start=min(start,max(0,total-visible))
    _move_viewport(v,'action',getattr(v,'_maintenance_scroll',0),start,visible,39,241,first=first)
    v._maintenance_scroll=start
    for slot in range(visible):
        index=first+start+slot
        if index<len(choices):
            _row(v,('action',index),choices[index],index,241+slot*39,35,None)
        else:
            if _cached(v,('empty',slot),(index,total)):
                v.lcd.draw_rectangle(1,BG,0,241+slot*39,259,278+slot*39)
                _forget(v,('action',index))
    _text(v,'action_count','%d/%d'%(selected+1,total) if total>visible else '',216,220,8,True,MUTED)
    owner=getattr(v.pd,'maintenance_pulse',None)
    color=getattr(owner,'display_color',None) if v._maintenance_page=='pulse' else None
    previous=v._maintenance_regions.get('color_patch')
    if (color is not None or previous is not None) and _cached(v,'color_patch',color):
        v.lcd.draw_rectangle(1,color if color is not None else BG,16,206,255,226)


def _report(v,screen):
    """Info-style area scroll: fixed header, bounded rows, exposed-band drawing."""
    from petrel.features.maintenance.ui.report import (cached_report_rows,REPORT_TOP,REPORT_ROW_HEIGHT,
                                    REPORT_VISIBLE_ROWS)
    choices=screen.choices
    if choices:
        v._draw_header_back(v._maintenance_selection == 0)
    color=WARNING if screen.tone in ('attention','danger') else ACCENT
    icon=screen.report_icon
    if _cached(v,'report_icon',icon):
        v.lcd.draw_rectangle(1,BG,20,40,43,63)
        if icon is not None: show_icon(v.lcd,ICON_LIBRARY_ID,icon,20,40)
    _text(v,'report_badge',screen.badge,50,40,26,True,color)
    for i,line in enumerate((textwrap.wrap(screen.heading,25)+['',''])[:2]):
        _text(v,('report_heading',i),line,50,57+i*17,25)
    rows=cached_report_rows(v,screen)
    visible,height=REPORT_VISIBLE_ROWS,REPORT_ROW_HEIGHT
    start=max(0,min(screen.report_offset,max(0,len(rows)-visible)))
    previous=getattr(v,'_maintenance_report_render_offset',0)
    if previous is not None:
        _move_viewport(v,'report',previous,start,visible,height,REPORT_TOP,first=0)
    v._maintenance_report_render_offset=start
    for slot in range(visible):
        index=start+slot
        y=REPORT_TOP+slot*height
        token=('report',index)
        if index>=len(rows):
            if _cached(v,('empty',('report',slot)),(index,len(rows))):
                v.lcd.draw_rectangle(1,BG,0,y,259,y+height-1)
                _forget(v,token)
            continue
        row=rows[index]
        shape=(y,height,row.choice,tuple((cell.column,len(cell.lines),cell.small,cell.role) for cell in row.cells))
        if _cached(v,('row',token),shape):
            _forget(v,token,keep=('row',))
            v.lcd.draw_rectangle(1,BG,0,y,259,y+height-1)
        for cell in row.cells:
            x=(24 if row.choice else 20)+cell.column*122
            cells=38 if cell.role in ('text','section') or row.choice and cell.small else (28 if row.choice else 18 if cell.small else 13)
            ink=ACCENT if cell.role=='section' else INK if cell.role in ('value','action') else MUTED
            top=y+(0 if len(cell.lines)>1 else 6 if cell.small else 4)
            for line,value in enumerate(cell.lines):
                _text(v,(token,cell.column,cell.role,line),value,x,top+line*12,cells,cell.small,ink)
        if row.choice:
            _cursor(v,token,y,height,v._maintenance_selection==row.choice)
    _scroll(v,start,len(rows),visible,REPORT_TOP,visible*height)


def draw_maintenance(v,screen):
    v._maintenance_selection=max(0,min(v._maintenance_selection,max(0,len(screen.choices)-1)))
    pinned=bool(screen.choices and screen.choices[0].action in ('back','home','result_back'))
    frame=(id(v.lcd),v._maintenance_page,screen.kind,screen.title,pinned)
    if frame!=v._maintenance_frame:
        v._maintenance_frame=frame
        v._maintenance_regions={}
        v._maintenance_scroll=0
        v._maintenance_report_render_offset=None
        v._list_render=None
        # Match the standard menu header exactly. The title bar has its own
        # background and cached Wi-Fi/clock/Klipper status indicators.
        v.Clear_Title_Bar()
        # Maintenance owns only the body; never cover the title color band.
        v.lcd.draw_rectangle(1,BG,0,31,271,359)
        v.Draw_Title(screen.title, back=pinned)
    v._maintenance_drawn_choices=tuple((c.action,c.value) for c in screen.choices)
    if screen.kind=='report':
        _report(v,screen)
    elif screen.kind=='home':
        _home(v,screen)
    elif screen.kind in ('list','care') and screen.choices:
        _list(v,screen)
    else:
        _detail(v,screen)
