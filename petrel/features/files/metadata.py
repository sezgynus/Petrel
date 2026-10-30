"""Normalize optional Moonraker preview fields without parsing G-code."""
from dataclasses import dataclass
import json
import math
import re
from petrel.ui.numbers import fixed


@dataclass(frozen=True)
class Filament:
    tool: int
    material: str
    color: int | None
    grams: float | None


@dataclass(frozen=True)
class PreviewDetails:
    seconds: float | None = None
    changes: int | None = None
    millimeters: float | None = None
    grams: float | None = None
    filaments: tuple = ()


@dataclass(frozen=True)
class PreviewData:
    jpeg: bytes | None
    details: PreviewDetails
    retryable: bool = True


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
        return value
    return None


def sequence(value):
    if isinstance(value, str):
        if len(value) > 16384:
            return []
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return [value]
        return parsed[:256] if isinstance(parsed, list) else [value]
    return value[:256] if isinstance(value, list) else []


def details_from_metadata(metadata):
    if not isinstance(metadata, dict):
        return PreviewDetails()
    materials = sequence(metadata.get('filament_type'))
    colors = sequence(metadata.get('filament_colors'))
    weights = sequence(metadata.get('filament_weights'))
    tools = metadata.get('referenced_tools')
    if not isinstance(tools, list):
        tools = [i for i, weight in enumerate(weights) if number(weight) is not None and weight > 0]
        if not tools and len(materials) == 1 and len(colors) <= 1:
            tools = [0]
    tools = sorted({tool for tool in tools[:256] if isinstance(tool, int) and not isinstance(tool, bool) and 0 <= tool < 256})
    filaments = []
    for tool in tools:
        material = materials[tool] if tool < len(materials) else (materials[0] if len(materials) == 1 else '--')
        material = ''.join(c for c in material if c.isprintable())[:10] if isinstance(material, str) else '--'
        color = colors[tool] if tool < len(colors) else None
        rgb565 = None
        if isinstance(color, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            r, g, b = (int(color[i:i+2],16) for i in (1,3,5))
            rgb565 = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        grams = number(weights[tool]) if tool < len(weights) else None
        filaments.append(Filament(tool, material or '--', rgb565, grams))
    changes = metadata.get('filament_change_count')
    if not isinstance(changes, int) or isinstance(changes, bool) or changes < 0:
        changes = None
    return PreviewDetails(number(metadata.get('estimated_time')), changes,
                          number(metadata.get('filament_total')), number(metadata.get('filament_weight_total')),
                          tuple(filaments))


def amount(value, unit):
    if value is None:
        return '--'+unit
    text = fixed(value,0 if unit in ('g','mm') else 2)
    if len(text) > 7:
        text = f'{value:.1e}'
    return text+unit


def filament_length(millimeters):
    if millimeters is None:
        return '--m'
    return amount(millimeters/1000,'m') if millimeters>1000 else amount(millimeters,'mm').replace('.00mm','mm')


def duration(seconds):
    if seconds is None:
        return '--'
    total = max(0,float(seconds))
    days, rest = divmod(total,86400)
    hours, rest = divmod(rest,3600)
    minutes, second = divmod(rest,60)
    parts = ([str(int(days))+'d'] if days else [])+([str(int(hours))+'h'] if hours else [])
    if minutes: parts.append(str(int(minutes))+'m')
    if second: parts.append(fixed(second)+'s')
    text = ' '.join(parts) or '--'
    if len(text)<=14:
        return text
    minutes = int(total//60)
    return '%dh %02dm'%divmod(minutes,60)
