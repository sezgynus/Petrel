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

def report_pages(sections):
    """Pack text and two-column facts into 132px without dropping any text."""
    blocks=[]
    for section in sections:
        if section.title:
            blocks.extend(('section',(line,),16) for line in _wrap(section.title,38))
        for paragraph in section.text:
            blocks.extend(('text',(line,),15) for line in _wrap(paragraph,38))
        for offset in range(0,len(section.facts),2):
            cells=[]
            for name,value in section.facts[offset:offset+2]:
                labels=_wrap(name,18)
                small=len(str(value))>13
                values=_wrap(value,18 if small else 13)
                cells.append((labels,values,small))
            height=max(len(c[0])*12+4+len(c[1])*(12 if c[2] else 16)+6 for c in cells)
            # Bound unusually long friendly values by splitting into continued cells.
            while height>132:
                chunks=[]
                remaining=[]
                for labels,values,small in cells:
                    count=max(1,(122-min(len(labels),3)*12)//(12 if small else 16))
                    chunks.append((labels[:3],values[:count],small))
                    remaining.append((('Continued',),values[count:],small))
                h=max(len(c[0])*12+4+len(c[1])*(12 if c[2] else 16)+6 for c in chunks)
                blocks.append(('facts',tuple(chunks),h))
                cells=[c for c in remaining if c[1]]
                if not cells: break
                height=max(len(c[0])*12+4+len(c[1])*(12 if c[2] else 16)+6 for c in cells)
            if cells:
                blocks.append(('facts',tuple(cells),height))
    if not blocks:
        blocks=[('text',('No displayable measurement.',),15)]
    pages=[];page=[];used=0
    for block in blocks:
        if page and used+block[2]>132:
            pages.append(tuple(page));page=[];used=0
        page.append(block);used+=block[2]
    if page: pages.append(tuple(page))
    return tuple(pages)
