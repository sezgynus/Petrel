"""Mainsail default progress and time estimates, without I/O.

Reference: mainsail-crew/mainsail src/store/printer/getters.ts and gui state.
Remaining averages file and filament; ETA also includes the slicer estimate.
"""
import math
import time
from datetime import date


def number(value):
    return float(value) if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def progress(sd, metadata):
    start, end = number(metadata.get('gcode_start_byte')), number(metadata.get('gcode_end_byte'))
    position = number(sd.get('file_position'))
    if start and end and end > start and position is not None:
        return max(0., min(1., (position - start) / (end - start)))
    return max(0., min(1., number(sd.get('progress')) or 0.))


def estimates(stats, sd, metadata):
    if stats.get('state') in ('standby', 'complete', 'cancelled', 'error'):
        return None, None
    duration = number(stats.get('print_duration')) or 0.
    ratio = progress(sd, metadata)
    used, total = number(stats.get('filament_used')), number(metadata.get('filament_total'))
    slicer = number(metadata.get('estimated_time'))
    sources = []
    def add(value):
        # Mainsail rounds each source to seconds before averaging positives.
        if value is not None and math.isfinite(value):
            rounded = math.floor(value + .5)
            if rounded > 0:
                sources.append(rounded)
    if duration > 0 and ratio > 0:
        add(duration / ratio - duration)
    if duration > 0 and used is not None and total is not None and 0 < used < total:
        add(duration / (used / total) - duration)
    remaining = sum(sources) / len(sources) if sources else None
    if duration > 0 and slicer is not None and slicer > 0:
        add(slicer - duration)
    eta = sum(sources) / len(sources) if sources else None
    return remaining, eta


def finish_text(now, remaining):
    if remaining is None or not math.isfinite(remaining) or remaining <= 0:
        return 'Finish --:--'
    finish = now + remaining
    current, target = time.localtime(now), time.localtime(finish)
    days = (date(*target[:3]) - date(*current[:3])).days
    return 'Finish ~' + time.strftime('%H:%M', target) + (' +%d' % days if days > 0 else '')
