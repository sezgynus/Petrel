"""Existing display methods grouped by responsibility."""
from petrel.ui.theme import show_icon as show_theme_icon, draw_scrollbar
from petrel.artwork.resources import ICON_INFO_UPDATE_SELECTED, ICON_INFO_UPDATE_NORMAL
from petrel.ui.numbers import fixed, js_round
import textwrap
from petrel.features.software_update.updater import SoftwareUpdate
from petrel.features.info.qr import PROJECT_URL, draw_project_qr, extra_info_rows
from petrel.features.nfc.share_view import NFCURIShareComponent
from petrel.artwork.shared import PICTURE_ID as SHARED_PICTURE_ID
from petrel.features.info.system import wifi_signal_text
import logging
from petrel.hardware.dwin.driver import T5UIC1Display
from petrel.artwork.resources import ICON_MCU, ICON_MACHINE, ICON_HOST, ICON_SOFTWARE


class InfoViewMixin:
    def HMI_Info(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO:
            return
        items = self._info_items()
        max_scroll = max(0, len(items) + extra_info_rows() - 13)
        current = getattr(self, '_info_scroll', 0)
        if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            self._software_updater().cancel_confirmation()
        if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            steps = max(1, getattr(self, '_rotation_steps', 1))
            delta = steps if event == self.ENCODER_DIFF_CW else -steps
            target = max(0, min(max_scroll, current + delta))
            share_stop = next((i - 1 for i, item in enumerate(items)
                               if item[0] == 'nfc_share'), None)
            # Coalesced detents must land on an actionable control, not skip it.
            if share_stop is not None and (
                    current < share_stop <= target or target <= share_stop < current):
                target = share_stop
            self._info_scroll = target
            if target == current:
                return
            self.Draw_Info_Menu()
        elif event == self.ENCODER_DIFF_ENTER:
            if (any(kind == 'nfc_share' for kind, _, _ in items)
                    and current == next(i for i, item in enumerate(items)
                                        if item[0] == 'nfc_share') - 1):
                if self._start_nfc_share_popup():
                    self.lcd.update()
                return
            if items and items[-1][0] == 'update' and current == max_scroll:
                self._software_updater().start()
                self.Draw_Info_Menu()
                self.lcd.update()
                return
            self._info_scroll = 0
            if getattr(self, '_info_origin', self.MainMenu) == self.Control:
                self.checkkey = self.Control
                self.select_control.set(self.CONTROL_CASE_INFO)
                self.Draw_Control_Menu()
            else:
                self.select_page.set(next(i for i, entry in enumerate(self._home_entries()) if entry[0] == 'INFO'))
                self.Goto_MainMenu()
        self.lcd.update()

    def _draw_info_row(self, label, value, y):
        self._draw_menu_text(label, 8, y)
        self._draw_info_value(label, value, y)

    def _draw_info_value(self, label, value, y, clear=False):
        text = T5UIC1Display._panel_text(value)[:17]
        if clear:
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 120, y, 255, y + 15)
        color = self.lcd.Color_White
        if label == 'Network':
            state = text.strip().lower()
            if state == 'online':
                color = 0x07E0
            elif state == 'offline':
                color = 0xF800
        self.lcd.draw_text(False, False, self.lcd.font8x16, color,
                             self.lcd.Color_Bg_Black, 120, y, text)

    def _draw_info_section(self, label, y):
        text = T5UIC1Display._panel_text(label)[:24]
        palette = {
            'MACHINE': (0x07FF, ICON_MACHINE),
            'HOST': (0x4C7F, ICON_HOST),
            'SOFTWARE': (0x03DF, ICON_SOFTWARE),
            'NFC': (0x07FF, ICON_MCU),
        }
        key = text.upper()
        if key.startswith('MCU'):
            color, icon = 0x063B, ICON_MCU
        else:
            color, icon = palette.get(key, (self.lcd.Color_White, None))
        if icon is not None:
            show_theme_icon(self.lcd, self.ICON, icon, 8, y - 2)
        else:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Info, 8, y - 2)
        self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White,
                             self.lcd.Color_Bg_Black, 40, y+2, key)
        self.lcd.draw_rectangle(1, self.lcd.Line_Color, 40, y + 21, 255, y + 21)

    def _draw_info_update_button(self, y, selected):
        updater = self._software_updater()
        backing = 0x063B if selected else 0x2967
        foreground = 0x10C4 if selected else self.lcd.Color_White
        label = T5UIC1Display._panel_text(updater.label)[:25]
        token = (id(self.lcd), y, bool(selected), label)
        previous = getattr(self, '_info_update_render', None)
        if previous is None or previous[:3] != token[:3]:
            icon = ICON_INFO_UPDATE_SELECTED if selected else ICON_INFO_UPDATE_NORMAL
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 32, y-4, 239, y+23)
            show_theme_icon(self.lcd, self.ICON, icon, 32, y - 4)
        elif previous[3] != label:
            # Interior only: preserve curved edges when the updater label changes.
            self.lcd.draw_rectangle(1, backing, 46, y, 226, y + 19)
        if previous is None or previous != token:
            self.lcd.draw_text(False, False, self.lcd.font8x16, foreground,
                               backing, (272 - len(label) * 8) // 2, y + 2, label)
        self._info_update_render = token
        message = (updater.phase, updater.message)
        if getattr(self, '_info_update_message', None) == (y, message):
            return
        self._info_update_message = (y, message)
        if y - 48 >= 38:
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black,
                                    23, y - 48, 249, y - 8)
        if not updater.message or updater.phase in ('checking', 'updating', 'restarting', 'recovering'):
            return
        color = {'current': 0x07E0, 'available': 0xFFE0, 'dirty': 0xFFE0,
                 'confirm_recovery': 0xFFE0}.get(updater.phase, 0xF800)
        lines = textwrap.wrap(T5UIC1Display._panel_text(updater.message), width=28)[:2]
        first_y = y - (40 if len(lines) > 1 else 32)
        for index, text in enumerate(lines):
            line_y = first_y + index * 16
            if line_y >= 38:
                self.lcd.draw_text(False, False, self.lcd.font8x16, color,
                                   self.lcd.Color_Bg_Black,
                                   (272 - len(text) * 8) // 2, line_y, text)

    def _refresh_info_update_button(self):
        items = self._info_items()
        for index, (kind, _, _) in enumerate(items):
            if kind != 'update':
                continue
            y = 38 + (index + extra_info_rows() - getattr(self, '_info_scroll', 0)) * 24
            if 38 <= y < 350:
                self._draw_info_update_button(
                    y, getattr(self, '_info_scroll', 0)
                    == max(0, len(items) + extra_info_rows() - 13))
                self.lcd.update()
            break

    def _software_updater(self):
        if not hasattr(self, '_software_update'):
            self._software_update = SoftwareUpdate(self.pd)
        return self._software_update

    def _nfc_share_component(self):
        component = getattr(self, '_nfc_uri_share', None)
        if component is None:
            component = NFCURIShareComponent(self.pd.get_nfc_core())
            self._nfc_uri_share = component
        return component

    def _start_nfc_share_popup(self):
        component = self._nfc_share_component()
        if not component.visible:
            return False
        # Set popup state before submission; share events may arrive immediately.
        self._nfc_share_popup = 'waiting'
        try:
            future = component.start(PROJECT_URL)
            if future.done():
                future.result()  # Handle immediate rejection without a backend event.
        except Exception:
            logging.exception('Unable to begin NFC URI share')
            self._nfc_share_popup = 'failed'
        self._draw_nfc_share_popup()
        return True

    def _draw_nfc_share_popup(self):
        self._nfc_share_component().draw_popup(
            self, failed=self._nfc_share_popup == 'failed')

    def _finish_nfc_share_popup(self):
        if not getattr(self, '_nfc_share_popup', None):
            return
        self._nfc_share_component().stop_animation()
        self._nfc_share_popup = None
        if self._uart_online and self.checkkey == self.Info:
            self._info_render_scroll = None
            self.Draw_Info_Menu()
            self.lcd.update()

    def _cancel_nfc_share_popup(self, redraw=True):
        if not getattr(self, '_nfc_share_popup', None):
            return
        self._nfc_share_component().stop_animation()
        self._nfc_share_popup = None
        self._nfc_share_component().cancel()
        if redraw and self._uart_online and self.checkkey == self.Info:
            self._info_render_scroll = None
            self.Draw_Info_Menu()
            self.lcd.update()

    def _info_items(self):
        info = self.pd.system_info
        cpu = info.get('host_cpu')
        ram = info.get('host_ram')
        temp = info.get('host_temp')
        items = [
            ('section', 'Machine', None),
            ('row', 'Size', self.pd.MACHINE_SIZE),
            ('row', 'Network', info.get('network', 'Unknown')),
            ('row', 'Wi-Fi', info.get('wifi_ssid', 'Unavailable')),
            ('row', 'RSSI', wifi_signal_text(info.get('wifi_rssi'))),
            ('row', 'IP', info.get('ip', 'Unavailable')),
            ('section', 'Host', None),
            ('row', 'CPU', 'N/A' if cpu is None else str(js_round(cpu))+'%'),
            ('row', 'RAM', 'N/A' if ram is None else str(js_round(ram))+'%'),
            ('row', 'CPU temp', 'N/A' if temp is None else fixed(temp)+' C'),

        ]
        mcus = info.get('mcus') or ()
        if not mcus:
            items.extend((('section', 'MCU', None), ('row', 'Status', 'Unavailable')))
        for mcu in mcus:
            name = str(mcu.get('name', 'mcu'))
            load = mcu.get('load')
            temperature = mcu.get('temperature')
            items.extend((
                ('section', 'MCU: ' + name, None),
                ('row', 'Status', 'Connected'),
                ('row', 'Load', 'N/A' if load is None else str(js_round(load))+'%'),
                ('row', 'Temp', 'N/A' if temperature is None else fixed(temperature)+' C'),
            ))
        nfc = info.get('nfc') or {'status': 'Reading...'}
        items.extend((('section', 'NFC', None),
                      ('row', 'Status', nfc.get('status', 'Unavailable'))))
        if nfc.get('status') == 'Connected':
            for label, key in (('Model', 'model'), ('Firmware', 'firmware'),
                               ('Hardware', 'hardware'), ('libnfc', 'library'),
                               ('ISO14443A', 'iso_a'), ('ISO14443B', 'iso_b'),
                               ('FeliCa', 'felica'), ('NFC Sharing', 'ndef_uri')):
                items.append(('row', label, nfc.get(key, 'Unavailable')))
        items.extend([
            ('section', 'Software', None),
            (self._nfc_share_component().info_item(info.get('petrel', 'Unavailable'))
             or ('row', 'Petrel', info.get('petrel', 'Unavailable'))),
            ('row', 'Klipper', self.pd.SHORT_BUILD_VERSION),
            ('row', 'Moonraker', info.get('moonraker', 'Unavailable')),
            ('row', 'Mainsail', info.get('mainsail', 'Unavailable')),
            ('qr', 'Scan for project info', PROJECT_URL),
        ])
        items.append(('update', '', None))
        return items

    def Draw_Info_Menu(self):
        self.lcd.ensure_cached_picture(SHARED_PICTURE_ID)
        self.pd.refresh_system_info()
        items = self._info_items()
        max_scroll = max(0, len(items) + extra_info_rows() - 13)
        self._info_scroll = max(0, min(getattr(self, '_info_scroll', 0), max_scroll))
        previous = getattr(self, '_info_render_scroll', None)
        delta = self._info_scroll - previous if previous is not None else 0
        old_items = getattr(self, '_info_render_items', ())
        share_selected = (any(kind == 'nfc_share' for kind, _, _ in items)
                          and self._info_scroll == next(i for i, item in enumerate(items)
                                                          if item[0] == 'nfc_share') - 1)
        old_share_selected = (any(kind == 'nfc_share' for kind, _, _ in old_items)
                              and previous == next(i for i, item in enumerate(old_items)
                                                    if item[0] == 'nfc_share') - 1)
        same_layout = (previous is not None and
                       getattr(self, '_info_render_lcd', None) is self.lcd and
                       [(kind, label) for kind, label, _ in old_items] ==
                       [(kind, label) for kind, label, _ in items])
        distance = abs(delta) * 24
        incremental = same_layout and 0 < distance < 266
        stationary = same_layout and delta == 0
        band = (350 - distance, 350) if delta > 0 else (36, 36 + distance)
        if not stationary:
            self._nfc_share_component()._render = None
        if incremental:
            # Moving the viewport can evict the update control entirely. Its
            # screen-space cache cannot survive a scroll out and back to the
            # same coordinates, even when label, selection and message match.
            self._info_update_render = None
            self._info_update_message = None
            self.lcd.move_area(1, self.DWIN_SCROLL_UP if delta > 0 else self.DWIN_SCROLL_DOWN,
                               distance, self.lcd.Color_Bg_Black, 0, 36, 255, 349)
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 0, 36, 255, 37)
            # Scroll indicators belong to the fixed frame, not the moving list.
            if (previous == max_scroll or old_share_selected) != (
                    self._info_scroll == max_scroll or share_selected):
                self._draw_header_back(self._info_scroll < max_scroll and not share_selected)
        elif not stationary:
            self.Clear_Main_Window()
            self._info_update_render = None
            self._info_update_message = None
            self.Draw_Title('Info', back=True)
            self.Draw_Back_First(self._info_scroll < max_scroll and not share_selected)
        for index, (kind, label, value) in enumerate(items):
            if stationary or kind != 'qr':
                continue
            y = 38 + (index - self._info_scroll) * 24
            qr_top = y + 24
            draw_project_qr(self.lcd, qr_top,
                            top=max(38, band[0]) if incremental else 38,
                            bottom=min(350, band[1]) if incremental else 350)
        for index, (kind, label, value) in enumerate(items):
            offset = extra_info_rows() if kind == 'update' else 0
            y = 38 + (index + offset - self._info_scroll) * 24
            if not 38 <= y < 350:
                if incremental and kind == 'update' and y == 350:
                    self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 32, 346, 239, 349)
                continue
            exposed = incremental and (band[0] <= y < band[1] or
                                       (kind == 'section' and y == 38))
            if (stationary or (incremental and not exposed)) and kind not in ('update', 'nfc_share'):
                if (kind == 'row' and
                        T5UIC1Display._panel_text(value)[:17] !=
                        T5UIC1Display._panel_text(old_items[index][2])[:17]):
                    self._draw_info_value(label, value, y, clear=True)
                continue
            if kind == 'qr':
                self._draw_menu_text(label, 48, y)
            elif kind == 'nfc_share':
                if not stationary:
                    self._draw_menu_text(label, 8, y)
                if (not stationary or
                        T5UIC1Display._panel_text(value)[:17] !=
                        T5UIC1Display._panel_text(old_items[index][2])[:17]):
                    self._draw_info_value(label, value, y, clear=True)
                self._nfc_share_component().draw_button(self, y, share_selected)
            elif kind == 'update':
                self._draw_info_update_button(y, self._info_scroll == max_scroll)
            elif kind == 'section':
                self._draw_info_section(label, y)
            else:
                self._draw_info_row(label, value, y)
        if not stationary:
            # The list ends at 349; the dashboard starts at STATUS_Y (360).
            # Pixels in this fixed gutter never participate in move_area.
            # Clear old QR fragments here, including those from earlier renders.
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black,
                                    0, 350, 255, self.STATUS_Y - 1)
        if not stationary:
            # The fixed gutter is wider than the scrollbar itself. Remove
            # edge fragments without touching retained content or dashboard.
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black,
                                    256, 36, 271, self.STATUS_Y - 1)
            draw_scrollbar(self.lcd, self._info_scroll, max_scroll + 13, 13, y=36, height=303)
        self._info_render_scroll = self._info_scroll
        self._info_render_items = items
        self._info_render_lcd = self.lcd
