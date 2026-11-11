"""Existing display methods grouped by responsibility."""
from petrel.features.buzzer.heater_events import heater_ready
from petrel.ui.theme import show_icon as show_theme_icon, AXIS_HOMED_COLOR, AXIS_UNHOMED_COLOR, AXIS_UNKNOWN_COLOR
from petrel.artwork.resources import ICON_FAN_FIRST, ICON_FAN_LAST
from petrel.ui.numbers import fixed, fit_decimal
import math
from collections.abc import Mapping
import time
from petrel.hardware.dwin.driver import T5UIC1Display


class DashboardMixin:
    def _draw_status_field(self, method, *args):
        # Compare the values that the LCD actually displays, not raw telemetry.
        args = list(args)
        if method == 'show_icon':
            key = (method, args[-2], args[-1])
        else:
            key = (method, args[-3], args[-2])
        cache = self._status_render
        previous = cache.get(key)
        value = list(args)
        if method == 'draw_integer_text':
            value[-1] = T5UIC1Display._format_scaled_decimal(
                self.lcd, args[-1], args[-4], 0, False)
        elif method == 'draw_signed_scaled_float_text':
            value[-1] = T5UIC1Display._format_scaled_decimal(
                self.lcd, args[-1], args[2], args[3], True)
        value = tuple(value)
        if previous == value:
            return
        if method == 'draw_text' and previous is not None:
            x, y = args[-3:-1]
            # Opaque 0x11 text already paints each cell's background. Clearing
            # old glyphs with a separate 0x05 packet races the physical panel:
            # a later text packet can arrive without the preceding clear.
            # Include trailing blank cells in this same opaque text command.
            width = (T5UIC1Display.FONT_SIZES[args[2]][0]
                     if isinstance(args[2], int) else self.STAT_CHR_W)
            occupied = max(len(previous[-1]), len(args[-1]))
            right = min(271, x + occupied * width - 1)
            if args[1]:
                args[-1] = args[-1].ljust(occupied)
            else:
                # Transparent text still needs an explicit background erase.
                height = (T5UIC1Display.FONT_SIZES[args[2]][1]
                          if isinstance(args[2], int) else 20)
                self.lcd.draw_rectangle(1, args[4], x, y, right, y + height - 1)
            # Invalidate any overlapping text/icon field, but never the
            # separately cached status markers below the glyph baseline.
            for other in list(cache):
                if (other[0] not in ('axis_home', 'dashboard_indicator')
                        and other != key and x < other[1] <= right
                        and y - 1 <= other[2] <= y + 19):
                    del cache[other]
        if method == 'show_icon':
            show_theme_icon(self.lcd, *args)
        else:
            getattr(self.lcd, method)(*args)
        cache[key] = value

    def _draw_dashboard_value(self, text, icon_x, y):
        # Native icons occupy a 20 px tile; every value begins 4 px after it.
        # No leading numeric padding: digit count never moves the first glyph.
        x = icon_x + 24
        cells = (min(272,icon_x+98)-x)//8
        if len(text)>cells:
            text = '#' * cells
        self._draw_status_field('draw_text',False,True,self.lcd.font8x16,
            self.lcd.Color_White,0x18C4,x,y,text)

    def _draw_axis_home_indicator(self, icon_x, homed):
        # 14x3 px, two pixels below the 20x20 XYZ icon; no text/icon overlap.
        color = (AXIS_HOMED_COLOR if homed is True else
                 AXIS_UNHOMED_COLOR if homed is False else AXIS_UNKNOWN_COLOR)
        key = ('axis_home', icon_x + 3, 470)
        if self._status_render.get(key) == color:
            return
        self.lcd.draw_rectangle(1, color, icon_x + 3, 470, icon_x + 16, 472)
        self._status_render[key] = color

    def _draw_dashboard_indicator(self, key, x, y, width, height, color):
        # Status-only rectangle: no asset, animation or full-screen invalidation.
        # Clearing a marker paints the exact previous footprint in dashboard BG.
        cache_key = ('dashboard_indicator', key)
        previous = self._status_render.get(cache_key)
        if previous == color:
            return
        self.lcd.draw_rectangle(1, 0x18C4 if color is None else color,
                                x, y, x + width - 1, y + height - 1)
        self._status_render[cache_key] = color

    def _draw_heater_indicator(self, key, x, y, heater):
        cache_key = ('dashboard_indicator', key)
        previous = self._status_render.get(cache_key)
        color = AXIS_UNKNOWN_COLOR
        if isinstance(heater, Mapping):
            actual, target = heater.get('temperature'), heater.get('target')
            if (isinstance(actual, (int, float)) and not isinstance(actual, bool)
                    and isinstance(target, (int, float)) and not isinstance(target, bool)
                    and math.isfinite(actual) and math.isfinite(target)):
                if target <= 0:
                    color = self.lcd.Line_Color  # Heat disabled
                else:
                    # 2 C entry / 3 C exit hysteresis suppresses threshold flicker.
                    ready = heater_ready(actual, target, previous == AXIS_HOMED_COLOR)
                    color = AXIS_HOMED_COLOR if ready else AXIS_UNHOMED_COLOR
        self._draw_dashboard_indicator(key, x + 3, y + 22, 14 if key == 'bed_heat' else 12,
                                       3, color)

    def _draw_status_decimal(self, value, x, y):
        # Only the two bounded Z fields use this cache. Formatting runs when
        # their raw input changes; redraws still use the normal LCD diff cache.
        cache = getattr(self, '_status_decimal_values', None)
        if cache is None:
            cache = self._status_decimal_values = {}
        key = (x,y)
        previous = cache.get(key)
        if previous is None or previous[0] != value:
            previous = (value,fit_decimal(value,6).ljust(6))
            cache[key] = previous
        self._draw_dashboard_value(previous[1],x-24,y)

    def _sync_fan_animation(self, visible, force=False):
        percent = max(0, min(100, round(self.pd.thermalManager['fan_speed'][0])))
        interval = max(1, min(255, round(100 / percent))) if visible and percent else 0
        key = (id(self.lcd), getattr(self, '_uart_epoch', 0), interval)
        if not force and key == getattr(self, '_fan_animation_key', None):
            return
        previous = getattr(self, '_fan_animation_key', None)
        if interval and (force or previous is None or not previous[2]):
            self.lcd.draw_rectangle(1, 0x18C4, 200, 380, 219, 399)
        if interval or (previous is not None and previous[2]):
            self.lcd.configure_animation(1, bool(interval), self.ICON,
                ICON_FAN_FIRST, ICON_FAN_LAST, 200, 380, interval or 1,
                restart_from_first=force or previous is None or not previous[2])
        self._fan_animation_key = key
        if visible and not interval:
            self.lcd.draw_rectangle(1, 0x18C4, 200, 380, 219, 399)
            # Match the opaque native animation path, including its backing.
            self.lcd.show_icon(self.ICON, ICON_FAN_FIRST, 200, 380, background=True)

    def Draw_Status_Area(self, with_update):
        if getattr(self, 'checkkey', None) in (self.MMUMenu, self.Tune, self.TuneEdit, self.PrintErrorDetails):
            self._sync_fan_animation(False)
            self._status_render = {}
            return
        # Compact dashboard: temperatures / speed / fan, bed / flow / Z offset,
        # then interpolated live X/Y/Z positions.
        layout = (id(self.lcd), self.pd.HAS_HOTEND, self.pd.HAS_FAN,
                  self.pd.HAS_HEATED_BED, self.pd.HAS_ZOFFSET_ITEM)
        redraw = layout != getattr(self, '_status_layout', None) or not with_update
        if redraw:
            self._status_layout = layout
            self._status_render = {}
            self.lcd.draw_rectangle(1, 0x18C4, 0,
                self.STATUS_Y, self.lcd.DWIN_WIDTH - 1, self.lcd.DWIN_HEIGHT - 1)

            self.lcd.draw_line(self.lcd.Line_Color, 12, 363, 259, 363)
        y1, y2, y3 = 380, 414, 448
        # Temperature fields need enough width for "actual/target". Keep them
        # in a wider left column and compact the two telemetry columns.
        x1, x2, x3 = 4, 102, 200
        value1, value2, value3 = 28, 126, 224
        # Use already subscribed Klipper state; dashboard markers do not poll.
        state = self.pd.state
        status = state.status if state.ready else {}
        hotend_name = getattr(getattr(self.pd.capabilities, 'active_hotend', None),
                              'name', None)
        hotend = status.get(hotend_name) if hotend_name else None
        bed = status.get('heater_bed')

        if self.pd.HAS_HOTEND:
            self._draw_status_field('show_icon',self.ICON,self.ICON_HotendTemp,x1,y1)
            temps = self.pd.thermalManager['temp_hotend'][0]
            self._draw_dashboard_value('%d/%d'%(temps['celsius'],temps['target']),x1,y1)
            self._draw_heater_indicator('hotend_heat', x1, y1, hotend)
            can_extrude = hotend.get('can_extrude') if isinstance(hotend, Mapping) else None
            self._draw_dashboard_indicator(
                'extrude_ready', x1 + 16, y1 + 22, 4, 3,
                AXIS_HOMED_COLOR if can_extrude is True else
                AXIS_UNHOMED_COLOR if can_extrude is False else AXIS_UNKNOWN_COLOR)

        # Match the established dashboard behavior: alternate speed override
        # and instantaneous Klipper toolhead velocity in the same field.
        phase = int(time.monotonic() / 2.0) & 1
        self._draw_status_field('show_icon', self.ICON, self.ICON_Speed, x2, y1)
        if phase:
            speed_text = '{:.0f}%'.format(self.pd.feedrate_percentage)
        else:
            speed_text = fixed(abs(self.pd.live_velocity))+'mm/s'
        self._draw_dashboard_value(speed_text,x2,y1)
        self._draw_dashboard_indicator(
            'speed_override', x2 + 3, y1 + 22, 14, 3,
            AXIS_UNHOMED_COLOR if state.ready and self.pd.feedrate_percentage != 100
            else None)

        if self.pd.HAS_FAN:
            self._sync_fan_animation(True, force=redraw)
            percent = max(0, min(100, round(self.pd.thermalManager['fan_speed'][0])))
            self._draw_dashboard_value(str(percent)+'%',x3,y1)

        if self.pd.HAS_HEATED_BED:
            self._draw_status_field('show_icon',self.ICON,self.ICON_BedTemp,x1,y2)
            temps = self.pd.thermalManager['temp_bed']
            self._draw_dashboard_value('%d/%d'%(temps['celsius'],temps['target']),x1,y2)
            self._draw_heater_indicator('bed_heat', x1, y2, bed)

        # The extrusion field alternates between M221 flow override and
        # instantaneous volumetric flow so both fit without sacrificing XYZ.
        self._draw_status_field('show_icon', self.ICON, self.ICON_StepE, x2, y2)
        if phase:
            flow_text = '{:.0f}%'.format(self.pd.flow_percentage)
        else:
            value = max(0.,self.pd.volumetric_flow)
            # Three digits plus a decimal and unit exceed this 74 px column.
            flow_text = fixed(value,1 if value<100 else 0)+'mm3/s'
        self._draw_dashboard_value(flow_text,x2,y2)
        self._draw_dashboard_indicator(
            'flow_override', x2 + 3, y2 + 22, 14, 3,
            AXIS_UNHOMED_COLOR if state.ready and self.pd.flow_percentage != 100
            else None)

        if self.pd.HAS_ZOFFSET_ITEM:
            self._draw_status_field('show_icon', self.ICON, self.ICON_Zoffset, x3, y2)
            self._draw_status_decimal(self.pd.BABY_Z_VAR,value3,y2)
            # The active mesh, not the set of saved profiles, controls compensation.
            mesh = status.get('bed_mesh')
            matrix = mesh.get('mesh_matrix') if isinstance(mesh, Mapping) else None
            self._draw_dashboard_indicator(
                'mesh_active', x3 + 8, y2 + 22, 4, 4,
                AXIS_HOMED_COLOR if isinstance(matrix, (tuple, list)) and
                bool(matrix) and isinstance(matrix[0], (tuple, list)) and
                bool(matrix[0]) else None)

        positions = self.pd.live_position
        # Read the already-subscribed authoritative Klipper state, not cached
        # position flags which may outlive a disconnect or Klipper restart.
        homed_axes = status.get('toolhead', {}).get('homed_axes')
        if not isinstance(homed_axes, str) or any(axis not in 'xyz' for axis in homed_axes):
            homed_axes = None
        for axis, icon, xpos, value_x, position in (
                ('x', self.ICON_MaxSpeedX, x1, value1, positions[0]),
                ('y', self.ICON_MaxSpeedY, x2, value2, positions[1]),
                ('z', self.ICON_MaxSpeedZ, x3, value3, positions[2])):
            self._draw_status_field('show_icon', self.ICON, icon, xpos, y3)
            self._draw_axis_home_indicator(xpos, None if homed_axes is None else axis in homed_axes)
            if value_x == value3:
                self._draw_status_decimal(position,value_x,y3)
            else:
                self._draw_dashboard_value(fixed(position,2),xpos,y3)
