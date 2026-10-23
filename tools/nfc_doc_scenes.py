"""NFC documentation scenes; registered for CI and the manual full render."""
from unittest.mock import Mock
from spoolman_tags import Spool, BindingPlan

SPECS = (
    ('nfc-home', 'home', 'NFC card and action menu', 'NFC kart ve işlem menüsü'),
    ('nfc-emergency-waiting', 'emg_wait', 'Capture a new emergency tag', 'Yeni acil durdurma kartı okutma'),
    ('nfc-emergency-confirm', 'emg_confirm', 'Confirm the emergency tag UID', 'Acil durdurma kartının UID onayı'),
    ('nfc-spool-list', 'list', 'Spoolman inventory with identity and color', 'Kimlik ve renk ile Spoolman envanteri'),
    ('nfc-spool-detail', 'detail', 'Spool identity and HEX color', 'Makara kimliği ve HEX rengi'),
    ('nfc-spool-multicolor', 'multicolor', 'Long filament name and multiple colors', 'Uzun filament adı ve çoklu renk'),
    ('nfc-spool-waiting', 'waiting', 'Native spool tag capture popup', 'Native makara kartı okutma popup penceresi'),
    ('nfc-spool-confirm', 'confirm', 'Confirm a captured spool tag', 'Okutulan makara kartını onaylama'),
    ('nfc-spool-transfer', 'transfer', 'Confirm moving a tag between spools', 'Kartı makaralar arasında taşıma onayı'),
    ('nfc-gate-choose', 'gate_choose', 'Choose a gate for the scanned spool', 'Okutulan makara için gate seçme'),
    ('nfc-gate-error', 'gate_error', 'Changed tag binding blocks gate assignment', 'Değişen kart eşleşmesi gate atamasını engeller'),
    ('nfc-gate-complete', 'gate_complete', 'Gate assignment confirmed by readback', 'Geri okumayla doğrulanan gate ataması'),
)

UID = '04:A2:B3:C4:D5:E6:F7'


def register(scene, canvas, finish):
    for name, mode, english, turkish in SPECS:
        def draw(mode=mode):
            view = canvas()
            selected = Spool(17, 'Example Filaments', 'Galaxy Red', 'PLA', ('FF0022',))
            multi = Spool(18, 'Example Filaments',
                          'Silk Aurora Blue Purple Green Multicolor Filament',
                          'PLA', ('2255FF', 'AA44DD', '22CC88'))
            core = Mock()
            core.global_action_uid.return_value = '01:02:03:04'
            view.pd.get_nfc_core = Mock(return_value=core)
            view.pd.sync_nfc_event = Mock(return_value=False)
            view.pd.system_info['rfid'] = {
                'status': 'Listening',
                'card': {'uid': UID, 'type': 'ISO14443A', 'atqa': '0004', 'sak': '08'}}
            view.checkkey = view.RFIDMenu
            view._rfid_selection = 0
            view._spool_selection = 0
            view._spool_selected = selected
            view._rfid_candidate = {'uid': UID}
            if mode == 'home':
                view._rfid_mode = 'info'
            elif mode.startswith('emg_'):
                view._rfid_mode = 'waiting' if mode == 'emg_wait' else 'confirm'
                view._rfid_candidate = {'uid': UID}
            elif mode == 'list':
                view._rfid_mode = 'spool_list'
                view._spool_offset, view._spool_more = 0, False
                view._spool_rows = (selected, multi,
                    Spool(19, 'Other Manufacturer', 'Natural PETG', 'PETG', ('EEE9CF',)))
                view._spool_selection = 1
            elif mode in ('detail', 'multicolor'):
                view._rfid_mode = 'spool_detail'
                if mode == 'multicolor':
                    view._spool_selected = multi
            elif mode == 'waiting':
                view._rfid_mode = 'spool_waiting'
            elif mode == 'confirm':
                view._rfid_mode = 'spool_confirm'
            elif mode == 'transfer':
                view._rfid_mode = 'spool_transfer'
                source = Spool(8, 'Earlier Manufacturer', 'Old PLA', 'PLA', ('FFFFFF',))
                view._spool_plan = BindingPlan(selected, UID, None, (source,))
            else:
                # Use the same MMU fixture as the other production gate scenes.
                from tools.render_docs_screenshots import sample
                view = canvas(sample(mmu=True))
                view.checkkey = view.NFCGateMenu
                phase = mode.removeprefix('gate_')
                view._nfc_gate_popup = {
                    'uid': UID, 'spool': selected, 'origin': view.MainMenu,
                    'epoch': view.pd.state.epoch, 'selection': 1,
                    'phase': phase, 'operation': None,
                    'message': ('Tag binding changed; scan again' if phase == 'error'
                                else 'Completed: Assign #17 to G2')}
                view._nfc_gate_draw()
                return finish(view)
            view.Draw_RFID_Menu()
            return finish(view)
        scene(name, 'nfc', english, turkish)(draw)
