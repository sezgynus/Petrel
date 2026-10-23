"""Pure, bounded report layout for the native 272x480 Maintenance panel."""
from dataclasses import dataclass
import textwrap

@dataclass(frozen=True, slots=True)
class ReportSection:
    title: str = ''
    text: tuple = ()
    facts: tuple = ()

def section_from_lines(title, lines):
    """Only friendly, already-whitelisted evidence enters this presentation."""
    sections=[]
    prose=[]
    facts=[]
    for line in lines:
        name,sep,value=str(line).partition(': ')
        if sep:
            if prose:
                sections.append(ReportSection(title,tuple(prose)))
                title='';prose=[]
            facts.append((name,value))
        else:
            if facts:
                sections.append(ReportSection(title,facts=tuple(facts)))
                title='';facts=[]
            prose.append(str(line))
    if prose or facts:
        sections.append(ReportSection(title,tuple(prose),tuple(facts)))
    return tuple(sections)

def _wrap(value,width):
    return tuple(textwrap.wrap(str(value),width,replace_whitespace=True) or ('',))

REPORT_TOP = 96
REPORT_ROW_HEIGHT = 24
REPORT_VISIBLE_ROWS = 10


@dataclass(frozen=True, slots=True)
class ReportCell:
    lines: tuple
    column: int = 0
    small: bool = True
    role: str = 'text'


@dataclass(frozen=True, slots=True)
class ReportRow:
    cells: tuple
    choice: int = 0


def report_rows(sections, choices=()):
    """Uniform pixel-scroll rows; facts are never selectable menu entries.

    Two small lines or one large value fit exactly in a 24-pixel band.
    Actions follow the complete report; Back stays outside the viewport.
    No content-dependent work is repeated on encoder ticks by the view cache.
    """
    rows=[]
    for section in sections:
        if section.title:
            rows.extend(ReportRow((ReportCell((line,),role='section'),))
                        for line in _wrap(section.title,38))
        for paragraph in section.text:
            rows.extend(ReportRow((ReportCell((line,)),)) for line in _wrap(paragraph,38))
        for offset in range(0,len(section.facts),2):
            pair=section.facts[offset:offset+2]
            labels=[_wrap(name,18) for name,value in pair]
            for at in range(0,max(map(len,labels)),2):
                rows.append(ReportRow(tuple(ReportCell(lines[at:at+2],col,role='label')
                    for col,lines in enumerate(labels) if lines[at:at+2])))
            values=[(_wrap(value,18 if len(str(value))>13 else 13),len(str(value))>13)
                    for name,value in pair]
            groups=[tuple(lines[i:i+(2 if small else 1)]
                          for i in range(0,len(lines),2 if small else 1))
                    for lines,small in values]
            for at in range(max(map(len,groups))):
                rows.append(ReportRow(tuple(ReportCell(parts[at],col,values[col][1],'value')
                    for col,parts in enumerate(groups) if at<len(parts))))
    if not rows:
        rows.append(ReportRow((ReportCell(('No displayable measurement.',)),)))
    for index,choice in enumerate(choices[1:],1):
        small=len(choice.label)>28
        lines=_wrap(choice.label,38 if small else 28)
        for at in range(0,len(lines),2 if small else 1):
            rows.append(ReportRow((ReportCell(lines[at:at+(2 if small else 1)],small=small,role='action'),),index))
    return tuple(rows)


def report_navigation(rows, choices, position):
    """Scroll immediately, then focus real actions; wrap in both directions."""
    maximum=max(0,len(rows)-REPORT_VISIBLE_ROWS)
    actions=max(0,len(choices)-1)
    count=maximum+1+actions
    position=position%count
    selected=max(0,position-maximum)
    offset=min(position,maximum)
    if selected:
        first=next((i for i,row in enumerate(rows) if row.choice==selected),maximum)
        offset=min(first,maximum)
    return position,offset,selected,count


def cached_report_rows(view,screen):
    source=(screen.sections,tuple(c.label for c in screen.choices))
    if getattr(view,'_maintenance_report_source',None)!=source:
        view._maintenance_report_source=source
        view._maintenance_report_rows=report_rows(screen.sections,screen.choices)
    return view._maintenance_report_rows
