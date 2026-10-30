"""NFC documentation scenes; registered for CI and the manual full render."""
from concurrent.futures import Future
from unittest.mock import Mock
from petrel.features.spoolman.tags import Spool, BindingPlan

SPECS = (
    ('nfc-home', 'home', 'NFC card and action menu', 'NFC kart ve işlem menüsü'),
    ('nfc-emergency-waiting', 'emg_wait', 'Capture a new emergency tag', 'Yeni acil durdurma kartı okutma'),
    ('nfc-emergency-confirm', 'emg_confirm', 'Confirm the emergency tag UID', 'Acil durdurma kartının UID onayı'),
    ('nfc-emergency-assigned', 'emg_assigned', 'Replace or remove the saved emergency tag', 'Kayıtlı acil durdurma kartını değiştirme veya kaldırma'),
    ('nfc-settings-enabled', 'settings_enabled', 'LCD reader configuration, feature enabled in Kconfig', 'Kconfig ile açılmış NFC için LCD okuyucu ayarları'),
    ('nfc-settings-disabled', 'settings_disabled', 'LCD settings while NFC is disabled in setup', 'Kurulumda NFC kapalı iken LCD ayarları'),
    ('nfc-settings-model', 'settings_model', 'Choose the reader model', 'Okuyucu modeli seçimi'),
    ('nfc-settings-interface', 'settings_interface', 'Choose the reader interface', 'Okuyucu arayüzü seçimi'),
    ('nfc-settings-port', 'settings_port', 'Choose a discovered reader port (example)', 'Bulunan okuyucu portunu seçme (örnek)'),
    ('nfc-test-wait', 'settings_wait', 'Connection test waiting for the worker', 'Bağlantı testi worker sonucunu bekliyor'),
    ('nfc-test-ok', 'settings_ok', 'Successful reader connection test (simulated)', 'Başarılı okuyucu bağlantı testi (örnek)'),
    ('nfc-test-fail', 'settings_fail', 'Failed reader connection test (simulated)', 'Başarısız okuyucu bağlantı testi (örnek)'),
    ('info-share-ready', 'share_ready', 'Connected NFC reader exposes inline link sharing', 'Bağlı NFC okuyucuyla satır içi bağlantı paylaşımı'),
    ('info-share-selected', 'share_selected', 'Focused inline NFC share control', 'Seçili satır içi NFC paylaşma simgesi'),
    ('nfc-share-waiting', 'share_waiting', 'NFC link sharing waits for a phone', 'NFC bağlantı paylaşımı telefon bekliyor'),
    ('nfc-share-failed', 'share_failed', 'Failed NFC share can be closed', 'Başarısız NFC paylaşımını kapatma'),
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
            if mode.startswith('settings_'):
                # The GPIO-isolated fixture retains its own imported class,
                # just as tests/test_nfc_settings.py does. Use that exact type
                # so production validation does not reset the example to Select.
                settings_type = view._nfc_config.__func__.__globals__['NFCSettings']
                value = settings_type(port='/dev/ttyUSB0')
                view._nfc_values = view._nfc_saved = value
                view._nfc_confirmed = dict(model=True, interface=True, port=True)
                view._nfc_enabled = lambda: mode != 'settings_disabled'
                view._nfc_port_choices = (('PN532', 'UART'), ('/dev/ttyUSB0', '/dev/ttyAMA0'))
                view._nfc_selection = 0
                view.checkkey = view.NFCSettingsMenu
                field = mode.removeprefix('settings_')
                if field in ('model', 'interface', 'port'):
                    view._nfc_choice_field = field
                    view._nfc_choice_options = view._nfc_options(field)
                    view._nfc_choice_selection = 1
                    view.checkkey = view.NFCChoiceMenu
                    view.Draw_NFC_Choice_Menu()
                else:
                    if field in ('wait', 'ok', 'fail'):
                        view._nfc_selection = 7
                        view._nfc_test_values = value
                        view._nfc_test_state = {'ok': 'OK', 'fail': 'Fail'}.get(field)
                        view._nfc_test_future = Future() if field == 'wait' else None
                    view.Draw_NFC_Settings_Menu()
                return finish(view)
            elif mode.startswith('share_'):
                core.get_capabilities.return_value = {'ndef_uri_emulation': True}
                core.is_ready.return_value = True
                from petrel.features.nfc.share_view import NFCURIShareComponent
                view._nfc_uri_share = NFCURIShareComponent(core)
                view.pd.system_info['nfc'] = {'status': 'Connected', 'model': 'PN532',
                    'firmware': '1.6', 'hardware': 'PN532', 'library': '1.8.0',
                    'iso_a': 'Yes', 'iso_b': 'Yes', 'felica': 'Yes', 'ndef_uri': 'Supported'}
                view.checkkey = view.Info
                items = view._info_items()
                index = next(i for i, item in enumerate(items) if item[0] == 'nfc_share')
                view._info_scroll = max(0, index - (1 if mode != 'share_ready' else 2))
                view.Draw_Info_Menu()
                if mode in ('share_waiting', 'share_failed'):
                    view._nfc_share_popup = 'failed' if mode == 'share_failed' else 'waiting'
                    view._draw_nfc_share_popup()
                return finish(view)
            elif mode == 'home':
                view._rfid_mode = 'info'
            elif mode.startswith('emg_'):
                view._rfid_mode = {'emg_wait': 'waiting', 'emg_confirm': 'confirm',
                                   'emg_assigned': 'emg'}[mode]
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
                # Gate assignment owns the full screen, including the dashboard area.
                return finish(view, dashboard=False)
            view.Draw_RFID_Menu()
            return finish(view)
        scene(name, 'nfc', english, turkish)(draw)
