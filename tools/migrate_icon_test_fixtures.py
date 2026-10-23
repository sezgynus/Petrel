#!/usr/bin/env python3
"""Update regression fixtures that intentionally asserted pre-migration physical IDs.

The production migration itself is verified independently. These updates do not
weaken behavioral assertions; they align expected icon selectors with the
documented id-redundancy-cleanup.json physical ID mapping.
"""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def edit(filename,pairs):
    p=ROOT/'tests'/filename
    s=p.read_text()
    for before,after in pairs:
        if before not in s:raise RuntimeError(f'Missing expected {before!r} in {filename}')
        s=s.replace(before,after)
    p.write_text(s)

edit('test_emulator.py',[
 ('ICON_LIBRARY_ID, 109, 17, 130','ICON_LIBRARY_ID, 99, 17, 130'),
 ('ICON_LIBRARY_ID, 195, 199','ICON_LIBRARY_ID, 181, 185'),
 ('self.assets.icon(ICON_LIBRARY_ID, 195).size','self.assets.icon(ICON_LIBRARY_ID, 181).size'),
 ('for icon in (0, 1, 15, 154, 199):','for icon in (0, 1, 15, 142, 185):'),
 ('self.assets.icon(ICON_LIBRARY_ID, 200)','self.assets.icon(ICON_LIBRARY_ID, 186'),
])
edit('test_ui_events.py',[
 ("                patch.object(ui.PetrelDisplay, 'HMI_ShowBoot'), \\\n",''),
])
edit('test_audit_rendering.py',[
 ('bytes((0x20 | ICON_LIBRARY_ID, 111))','bytes((0x20 | ICON_LIBRARY_ID, 101))'),
 ("('Machine',112),('Host',113),('Software',57)","('Machine',102),('Host',103),('Software',54)"),
])
edit('test_bed_mesh.py',[
 ('_mesh_menu_entries()[1][2], 153','_mesh_menu_entries()[1][2], 142'),
 ("('CALIBRATE',179),('VIEWER',170)","('CALIBRATE',165),('VIEWER',158)"),
])
edit('test_boot_splash.py',[
 ('bytes((0xC0, ICON_LIBRARY_ID, 195, 199, 10))',
  'bytes((0xC0, ICON_LIBRARY_ID, 181, 185, 10))'),
])
edit('test_capabilities.py',[
 ('result.ICON_CaseLight, 155','result.ICON_CaseLight, 143'),
])
edit('test_card_scan_popup.py',[
 ('ICON_LIBRARY_ID, 45, 56, 56, 116, 20',
  'ICON_LIBRARY_ID, 42, 53, 56, 116, 20'),
])
edit('test_graphite_theme.py',[
 ('[159, 160, 161, 162]','[147, 148, 149, 150]'),
 ('[155, 156]','[143, 144]'),
])
edit('test_home_pages.py',[
 ('[(109,17,130),(59,145,130),','[(99,17,130),(56,145,130),'),
 ("entries[-3][2:], (41, 42)","entries[-3][2:], (38, 39)"),
 ("entries[-1][2:], (43, 44)","entries[-1][2:], (40, 41)"),
])
edit('test_maintenance_icons.py',[
 ('(114,115,116,117)','(104,105,106,107)'),
 ('{114,115,116,117}','{104,105,106,107}'),
 ('icon_for(sensors),20','icon_for(sensors),19'),
 ("'sensor_devices')),20","'sensor_devices')),19"),
 ("feature_icon('F02','fan'),32","feature_icon('F02','fan'),30"),
 ("feature_icon('M03','stepper_x'),19","feature_icon('M03','stepper_x'),18"),
 ("feature_icon('P03','probe'),169","feature_icon('P03','probe'),157"),
 ("feature_icon('S18','buzzer'),159","feature_icon('S18','buzzer'),147"),
 ('self.assertNotIn(31,TOPICS.values())','self.assertNotIn(29,TOPICS.values())'),
 ("Choice('Details','details')),31","Choice('Details','details')),29"),
 ("'unknown'))),171","'unknown'))),159"),
 ("'unknown'))),26","'unknown'))),24"),
])
edit('test_nfc_settings.py',[
 ("('Test connection', 115, ('Wait', True))","('Test connection', 105, ('Wait', True))"),
])
edit('test_nfc_share_ui.py',[
 ('ICON_LIBRARY_ID, 137, 92','ICON_LIBRARY_ID, 127, 92'),
 ('ICON_LIBRARY_ID, 136, 92','ICON_LIBRARY_ID, 126, 92'),
 ('c.args[1] in (136, 137)','c.args[1] in (126, 127)'),
 ('ICON_LIBRARY_ID, 124, 135, 56','ICON_LIBRARY_ID, 114, 125, 56'),
])
edit('test_print_focus.py',[
 ('p[-5] == 103','p[-5] == 93'),
])
edit('test_print_screen.py',[
 ('f[-5] == 105','f[-5] == 95'),
])
edit('test_screws_tilt.py',[
 ('self.assertEqual(row[2], 171)','self.assertEqual(row[2], 159)'),
 ("Draw_Menu_Line.assert_any_call(0, 172, 'Calculate')",
  "Draw_Menu_Line.assert_any_call(0, 160, 'Calculate')"),
])
edit('test_spool_view.py',[
 ('self.assertEqual(ICON_SPOOL_EMPTY, 75)','self.assertEqual(ICON_SPOOL_EMPTY, 65)'),
])
print('Physical icon-ID regression expectations migrated')
