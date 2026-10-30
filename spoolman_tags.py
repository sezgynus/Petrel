"""On-demand Spoolman catalogue and confirmed UID binding via Moonraker proxy.

No NFC hardware access. Run only on the existing bounded read worker.
Bindings use Spoolman's native Tags API, never an extra-field substitute.
"""
from dataclasses import dataclass, field
import math
import re
from urllib.parse import urlencode

from nfc_core import normalize_uid

PAGE_SIZE = 20


@dataclass(frozen=True)
class Spool:
    id: int
    vendor: str
    name: str
    material: str
    colors: tuple
    archived: bool = False
    remaining_percent: int | None = field(default=None, compare=False)
    assignment: tuple = ()


def colors(value):
    if not isinstance(value, str):
        return ()
    result = []
    for part in value.split(',')[:8]:
        code = part.strip().lstrip('#').upper()
        if re.fullmatch(r'[0-9A-F]{6}([0-9A-F]{2})?', code):
            result.append(code[:6])
    return tuple(result)


def remaining_percent(spool):
    """Same weight-based percentage used by the Home/MMU spool display."""
    try:
        remaining = float(spool['remaining_weight'])
        initial = spool.get('initial_weight')
        if initial is None:
            initial = (spool.get('filament') or {}).get('weight')
        initial = float(initial)
        if (not math.isfinite(remaining) or not math.isfinite(initial)
                or initial <= 0 or remaining < 0):
            return None
        return math.ceil(max(0, min(100, remaining / initial * 100)))
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def describe(raw):
    if not isinstance(raw, dict) or type(raw.get('id')) is not int or raw['id'] <= 0:
        raise ValueError('Invalid Spoolman spool')
    filament = raw.get('filament') or {}
    vendor = filament.get('vendor') or {}
    text = lambda value: str(value).strip()[:256] if value is not None else ''
    # Match Mainsail's gate assignment payload, independent of display labels.
    # Strip command delimiters and control characters before quoting G-code text.
    def command_text(value, fallback):
        return ''.join(c for c in str(value if value is not None else fallback)
                       if c not in '\"\'' and c.isprintable())
    color = colors(filament.get('color_hex'))
    temperature = filament.get('settings_extruder_temp')
    if type(temperature) is not int or temperature < -1:
        temperature = -1
    assignment = (command_text(filament.get('name'), 'Unknown'),
                  command_text(filament.get('material'), 'Unknown'),
                  color[0] if color else '000000', temperature)
    return Spool(raw['id'], text(vendor.get('name')) or 'Unknown',
                 text(filament.get('name')) or 'Unnamed',
                 text(filament.get('material')) or 'Unknown',
                 colors(filament.get('multi_color_hexes')) or colors(filament.get('color_hex')),
                 raw.get('archived') is True, remaining_percent(raw), assignment)


def tag_uids(raw):
    tags = raw.get('tags')
    if not isinstance(tags, list):
        raise ValueError('Spoolman Tags API unavailable')
    try:
        return tuple(sorted(normalize_uid(item['uid']) for item in tags))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('Invalid Spoolman tag data') from error


@dataclass(frozen=True)
class BindingPlan:
    target: Spool
    uid: str
    previous_uid: str | None
    sources: tuple
    target_tags: tuple = ()


class BindingConflict(ValueError):
    def __init__(self, plan):
        super().__init__('Tag move or replacement needs confirmation')
        self.plan = plan


class SpoolmanTags:
    def __init__(self, client):
        self.client = client

    def request(self, method, path, *, query=None, body=None):
        payload = {'request_method': method, 'path': path}
        if query:
            payload['query'] = urlencode(query)
        if body is not None:
            payload['body'] = body
        response = self.client.request('POST', '/server/spoolman/proxy', payload)
        if not isinstance(response, dict) or 'result' not in response:
            raise ValueError('Invalid Spoolman response')
        return response['result']

    def page(self, offset=0):
        if type(offset) is not int or offset < 0:
            raise ValueError('Invalid catalogue offset')
        raw = self.request('GET', '/v1/spool', query={
            'limit': PAGE_SIZE + 1, 'offset': offset, 'sort': 'id:asc',
            'allow_archived': 'false'})
        if not isinstance(raw, list) or len(raw) > PAGE_SIZE + 1:
            raise ValueError('Invalid Spoolman catalogue')
        return tuple(describe(item) for item in raw[:PAGE_SIZE]), len(raw) > PAGE_SIZE

    def candidate(self, spool_id):
        if type(spool_id) is not int or spool_id <= 0:
            raise ValueError('Invalid spool ID')
        raw = self.request('GET', '/v1/spool/%d' % spool_id)
        spool = describe(raw)
        if spool.id != spool_id or spool.archived:
            raise ValueError('Spool unavailable or archived')
        return raw, spool

    def lookup(self, uid):
        """Resolve a native spool tag without scan broadcasts or active-spool changes."""
        from nfc_core import normalize_uid
        uid = normalize_uid(uid)
        rows = self.request('GET', '/v1/spool', query={
            'tag': uid.replace(':', ''), 'allow_archived': 'true', 'limit': 2})
        if not isinstance(rows, list) or len(rows) > 1:
            raise ValueError('Invalid Spoolman tag lookup')
        if not rows:
            return None
        if uid not in tag_uids(rows[0]):
            raise ValueError('Spoolman tag lookup not supported')
        spool = describe(rows[0])
        return None if spool.archived else spool

    def assign(self, spool_id, uid, expected, approval=None):
        uid = normalize_uid(uid)
        wire_uid = uid.replace(':', '')
        raw, current = self.candidate(spool_id)
        if current != expected:
            raise ValueError('Spool changed; select again')
        target_tags = tag_uids(raw)
        # Native tag lookup is unique and includes archived spool owners.
        rows = self.request('GET', '/v1/spool', query={
            'tag': wire_uid, 'allow_archived': 'true', 'limit': 2})
        if not isinstance(rows, list) or len(rows) > 1:
            raise ValueError('Invalid Spoolman tag lookup')
        sources = []
        for item in rows:
            if uid not in tag_uids(item):
                raise ValueError('Spoolman tag lookup not supported')
            if item.get('id') != spool_id:
                sources.append(describe(item))
        plan = BindingPlan(expected, uid, None, tuple(sources), target_tags)
        if sources and approval != plan:
            raise BindingConflict(plan)
        latest, fresh = self.candidate(spool_id)
        if fresh != expected or tag_uids(latest) != target_tags:
            raise ValueError('Spool changed; select again')
        for source in sources:
            owner = self.request('GET', '/v1/spool/%d' % source.id)
            if describe(owner) != source or uid not in tag_uids(owner):
                raise ValueError('Tag owner changed; select again')
        writing = False
        try:
            for source in sources:
                writing = True
                # Some Moonraker proxies JSON-decode Spoolman's empty 204
                # unlink response and report an error after a successful DELETE.
                # Never replay it: fresh native tag readback decides the result.
                unlink_error = None
                try:
                    self.request('DELETE', '/v1/spool/%d/tag/%s' % (source.id, wire_uid))
                except Exception as error:
                    unlink_error = error
                owner = self.request('GET', '/v1/spool/%d' % source.id)
                if uid in tag_uids(owner):
                    raise ValueError('Old tag removal not confirmed') from unlink_error
            if sources:
                latest, fresh = self.candidate(spool_id)
                if fresh != expected or tag_uids(latest) != target_tags:
                    raise ValueError('Target spool changed during move')
            # Native POST returns a Tag, not a Spool. Other tags are preserved.
            writing = True
            result = self.request('POST', '/v1/spool/%d/tag' % spool_id,
                                 body={'uid': wire_uid})
            if not isinstance(result, dict) or normalize_uid(result.get('uid')) != uid:
                raise ValueError('Tag link not confirmed')
            # Success is visible only after the spool's actual Tags collection
            # contains the UID; an extra.nfc_id value is never sufficient.
            linked, _ = self.candidate(spool_id)
            if uid not in tag_uids(linked):
                raise ValueError('Tag missing from Spoolman Tags')
        except Exception as error:
            if sources and writing:
                raise ValueError('Move incomplete; check Spoolman Tags') from error
            raise
        return uid
