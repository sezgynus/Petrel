"""Existing PrinterData methods grouped by responsibility."""
import math
from petrel.ui.numbers import js_round


class CaseLightPrinterMixin:
    def case_light_state(self):
        snapshot = self.subscription.snapshot()
        value = snapshot['status'].get('output_pin case_light', {}).get('value')
        if snapshot['state'] != 'ready' or not isinstance(value, (int, float)):
            return None
        if not math.isfinite(value) or not 0 <= value <= 1:
            return None
        return value > 0, js_round(value * 100)

    def set_case_light_brightness(self, percent):
        percent = float(percent)
        snapshot = self.subscription.snapshot()
        if not math.isfinite(percent) or not 0 <= percent <= 100:
            raise ValueError('Case light brightness out of range')
        if 'output_pin case_light' not in snapshot['objects']:
            raise ValueError('Case light output pin unavailable')
        settings = snapshot['settings'].get('output_pin case_light', {})
        if str(settings.get('pwm', False)).lower() not in ('true', '1'):
            if percent not in (0, 100):
                raise ValueError('Digital case light supports only on/off')
            return self.sendGCodeObserved('SET_PIN PIN=case_light VALUE={:.6f}'.format(percent / 100))
        scale = float(settings.get('scale', 1))
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError('Invalid case light scale')
        return self.sendGCodeObserved('SET_PIN PIN=case_light VALUE={:.6f}'.format(percent * scale / 100))
