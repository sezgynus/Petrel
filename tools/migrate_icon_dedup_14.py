#!/usr/bin/env python3
"""One-off cleanup of fourteen redundant Petrel icon IDs."""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

R = Path(__file__).resolve().parents[1]
A = {33:30, 152:20, 154:28, 173:29, 176:18, **{68+i:61+i for i in range(7)}}
D = {16,21}
gone = D | set(A)
ids = [i for i in range(200) if i not in gone]
compact = {n:i for i,n in enumerate(ids)}
M = {n:compact[A.get(n,n)] for n in range(200) if n not in D}
assert len(ids)==186 and len(A)==12
J=R/'assets/icons'
S=R/'assets/icon-source'

def change(p,func):
    p=R/p
    before=p.read_text()
    after=func(before)
    assert after!=before, 'Missing edit in '+str(p)
    p.write_text(after)

def sub(s,x,y):
    assert s.count(x)==1,(x,s.count(x))
    return s.replace(x,y)

def constants(s):
    return re.sub(r'(?m)^(\s*ICON_\w+\s*=\s*)(\d{1,3})([ \t]*(?:#.*)?)$',
        lambda m:m[1]+str(M.get(int(m[2]),int(m[2])))+m[3],s)

def ui(s):
    s=sub(s,'    ICON_Bar = 16\n','')
    s=sub(s,'    ICON_ABSPreheat = 21\n','')
    for name in ('HMI_ShowBoot','Item_Prepare_ABS'):
        s,n=re.subn(r'(?ms)^    def '+name+r'\(.*?\n.*?(?=^    def |^    # ----)',
            '',s,count=1)
        assert n==1,name
    s=constants(s)
    assert not any(x in s for x in ('ICON_Bar','ICON_ABSPreheat','HMI_ShowBoot','Item_Prepare_ABS'))
    return s

def resources(s):
    s=constants(s)
    s=sub(s,'SPOOL_LEFT_FLANGES = {width: 60 + width for width in range(1, 8)}',
            'SPOOL_LEFT_FLANGES = {width: 57 + width for width in range(1, 8)}')
    s=sub(s,'SPOOL_RIGHT_FLANGES = {width: 67 + width for width in range(1, 8)}',
            'SPOOL_RIGHT_FLANGES = SPOOL_LEFT_FLANGES')
    return sub(s,'# Dense directory: add the next icon at ID 200; 200..255 are free.',
                 '# Dense directory: add the next icon at ID 186; 186..255 are free.')

def generators(s):
    return re.sub(r'(?m)^(\s*)(\d{1,3})(:\s*[\(\[])',
        lambda m:m[1]+str(M.get(int(m[2]),int(m[2])))+m[3],s)

def native_test(s):
    a=s.index('        expected = {')
    b=s.index('\n        for icon, size',a)
    section=re.sub(r'\b(\d{1,3})(:\s*\()',lambda m:str(M[int(m[1])])+m[2],s[a:b])
    return s[:a]+section+s[b:]

def readme(s,tr):
    values=({
        '**200 ikon, 0–199 ID’leri**':'**186 ikon, 0–185 ID’leri**',
        '**200–255 boştur**':'**186–255 boştur**',
        '**200** ID’siyle':'**186** ID’siyle',
        '**200** ile başlayan **56 boş ID**':'**186** ile başlayan **70 boş ID**',
        '**23/24/25**':'**21/22/23**',
        '**5.379 kullanılabilir bayt boşluk**':'**18.247 kullanılabilir bayt boşluk**',
        '**70.913 bayttır**':'**83.781 bayttır**',
        '**PETICO05** metadata sürümü':'**PETICO06** metadata sürümü',
        'PETICO01/PETICO02/PETICO03/PETICO04 kaydıyla':'PETICO01/PETICO02/PETICO03/PETICO04/PETICO05 kaydıyla',
    } if tr else {
        '**200 icons, IDs 0–199**':'**186 icons, IDs 0–185**',
        '**200–255 are free**':'**186–255 are free**',
        'use **200** for the next icon':'use **186** for the next icon',
        '**56 free IDs**, starting at **200**':'**70 free IDs**, starting at **186**',
        '**23/24/25**':'**21/22/23**',
        '**5,379 usable free bytes**':'**18,247 usable free bytes**',
        '**70,913 usable bytes free**':'**83,781 usable bytes free**',
        'Metadata **PETICO05** distinguishes':'Metadata **PETICO06** distinguishes',
        'PETICO01/PETICO02/PETICO03/PETICO04 metadata':'PETICO01/PETICO02/PETICO03/PETICO04/PETICO05 metadata',
    })
    for a,b in values.items():s=sub(s,a,b)
    backtick=chr(96)
    s=sub(s,'('+backtick+'200.jpg'+backtick+', '+backtick+'assets/icon-source/200.svg'+backtick+')',
        '('+backtick+'186.jpg'+backtick+', '+backtick+'assets/icon-source/186.svg'+backtick+')')
    s=sub(s,'--ids 136 137','--ids 126 127')
    # Current resource-table ID cells only; never rewrite historical migration notes.
    name='## Güncel kaynaklar' if tr else '## Current resources'
    a=s.index(name);b=s.index('\n## ',a+len(name))
    rows=[]
    for line in s[a:b].splitlines(keepends=True):
        if line.startswith('|') and line.count('|')>=4 and not line.startswith('|---'):
            cells=line.split('|')
            if cells[2].strip() not in ('IDs','ID’ler'):
                cells[2]=re.sub(r'(?<!\d)\d{1,3}(?!\d)',
                    lambda m:str(M[int(m[0])]),cells[2])
                line='|'.join(cells)
        rows.append(line)
    s=s[:a]+''.join(rows)+s[b:]
    name='## Print butonları, switchler ve fan görselleri' if tr else '## Print buttons, switches and fan artwork'
    a=s.index(name);b=s.index('\n## ',a+len(name))
    v=s[a:b]
    v=re.sub(r'(?<!\d)(\d{2,3})[–-](\d{2,3})(?!\d)',
        lambda m:str(M[int(m[1])])+'–'+str(M[int(m[2])]),v)
    for l,r in ((81,82),(83,84),(193,194)):
        v=v.replace(str(l)+'/'+str(r),str(M[l])+'/'+str(M[r]))
    s=s[:a]+v+s[b:]
    if tr:
        t=('İkinci denetimde kullanılmayan eski açılış çubuğu (16) ve ABS ön ısıtma ikonu (21) kaldırıldı. '
           'Makara flanşları dahil 12 özdeş JPEG/SVG kopyası birleştirildi. '
           '**14 ID ve 12.868 JPEG baytı** kazanıldı. '
           '[Taşıma haritası](id-redundancy-cleanup.json) değişiklikleri kaydeder.\n\n')
        s=sub(s,'Temizlikte **40 kullanılmayan ikon**',
            t+'İlk temizlikte **40 kullanılmayan ikon**')
    else:
        t=('Second audit: removed unused boot bar (16), old ABS preheat (21), '
           'and 12 byte-identical JPEG/SVG copies, including seven spool flanges. '
           '**14 IDs and 12,868 JPEG bytes** reclaimed. '
           'See [migration map](id-redundancy-cleanup.json).\n\n')
        s=sub(s,'The cleanup removed **40 unused icons**',
            t+'The original cleanup removed **40 unused icons**')
    return s

def main():
    assert not (J/'id-redundancy-cleanup.json').exists()
    assert {int(p.stem) for p in J.glob('[0-9][0-9][0-9].jpg')}==set(range(200))
    reclaimed=sum((J/f'{i:03}.jpg').stat().st_size for i in gone)
    assert reclaimed==12868,reclaimed
    for dup,canon in A.items():
        for root,extension in ((J,'jpg'),(S,'svg')):
            a=root/f'{dup:03}.{extension}';b=root/f'{canon:03}.{extension}'
            assert a.exists() and b.exists() and a.read_bytes()==b.read_bytes(),(a,b)
    change('petrel_ui.py',ui)
    change('lcd_resources.py',resources)
    # The Maintenance icon selector has active literal numerical icon IDs.
    # Remap Python NUMBER tokens only; preserve feature strings, UI geometry and aliases.
    def maintenance_literal_ids(source):
        import io, tokenize
        tokens=list(tokenize.generate_tokens(io.StringIO(source).readline))
        updated=[]
        for token in tokens:
            if token.type==tokenize.NUMBER and token.string.isdecimal():
                old=int(token.string)
                if old in M:
                    token=token._replace(string=str(M[old]))
            updated.append(token)
        return tokenize.untokenize(updated)
    change('maintenance_icons.py',maintenance_literal_ids)

    change('icon_library.py',lambda s:sub(s,"MAGIC = b'PETICO05'","MAGIC = b'PETICO06'"))
    change('tools/render_button_backings.py',
        lambda s:sub(generators(s),'if index in (92, 93):','if index in (82, 83):'))
    def renderer(s):
        for x,y in ((76,84),(188,192),(180,187)):
            s=sub(s,f'{x} <= icon_id <= {y}',f'{M[x]} <= icon_id <= {M[y]}')
        return s
    change('tools/render_icon_sources.py',renderer)
    for p in ('assets/icon-source/rfid/render.py','assets/icon-source/nfc-settings/render.py'):
        change(p,generators)
    change('tests/test_native_custom_icons.py',native_test)
    change('tests/test_lcd_assets.py',lambda s:sub(s,'for icon in (43, 44):','for icon in (40, 41):'))
    change('tests/test_graphite_theme.py',lambda s:sub(s,'v.ICON_CloseMotor, 111','v.ICON_CloseMotor, 101'))
    def compact_test(s):
        s=sub(s,'id-native-confirm.json','id-redundancy-cleanup.json')
        return sub(s,'self.assertLessEqual(set(migration.values()), set(source_ids))',
            'self.assertLessEqual(set(migration.values()), set(source_ids))\n'
            '        self.assertEqual(len(source_ids), 186)\n'
            '        self.assertEqual(len(record["aliases"]), 12)\n'
            '        self.assertEqual(len(record["removed_ids"]), 2)')
    change('tests/test_compact_icon_ids.py',compact_test)
    change('tests/test_managed_icon_library.py',
        lambda s:sub(s,'if not 45 <= record[0] <= 56','if not 42 <= record[0] <= 53'))
    change('assets/icons/README.md',lambda s:readme(s,False))
    change('assets/icons/README_TR.md',lambda s:readme(s,True))
    manifest=json.loads((R/'docs/lcd-assets.json').read_text())
    del manifest['icons']['ICON_Bar'];del manifest['icons']['ICON_ABSPreheat']
    for x in manifest['icons'].values(): x['id']=M[x['id']]
    for root,extension in ((J,'jpg'),(S,'svg')):
        with TemporaryDirectory() as temporary:
            temporary=Path(temporary)
            for p in root.glob('[0-9][0-9][0-9].'+extension):
                shutil.move(p,temporary/p.name)
            for old in ids:
                p=temporary/f'{old:03}.{extension}'
                if p.exists():shutil.move(p,root/f'{compact[old]:03}.{extension}')
    sys.path.insert(0,str(R))
    import icon_library
    from tools.pack_icon_library import entries,validate_block_layout
    packed=icon_library.build_library()
    validate_block_layout(packed,2)
    assert sorted(i for i,*_ in entries(packed))==list(range(186))
    assert icon_library.build_library()==packed
    (R/'assets/emulator/2.ICO').write_bytes(packed)
    manifest['sha256']['2.ICO']=hashlib.sha256(packed).hexdigest()
    (R/'docs/lcd-assets.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    record={'from_commit':'07394809de0449c83c87a9837567e9692ccee06e',
      'removed_ids':sorted(D),'aliases':{str(x):y for x,y in sorted(A.items())},
      'mapping':{str(x):y for x,y in sorted(M.items())},
      'reclaimed_jpeg_bytes':reclaimed,'new_icon_count':186,
      'new_metadata_magic':'PETICO06'}
    (J/'id-redundancy-cleanup.json').write_text(json.dumps(record,indent=2)+'\n')
    print('PASS: 186 icons, 12868 reclaimed bytes,',len(packed)//32768,'Flash blocks')

if __name__=='__main__': main()
