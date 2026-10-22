"""On-demand Spoolman catalogue and confirmed UID binding via Moonraker proxy.

No NFC hardware access. Run only on the existing bounded read worker.
Spoolman's JSON-encoded text extra field nfc_id works with older releases too.
"""
from dataclasses import dataclass
import json
import re
from urllib.parse import urlencode

from nfc_core import normalize_uid

PAGE_SIZE = 20
TAG_FIELD = 'nfc_id'


@dataclass(frozen=True)
class Spool:
    id: int
    vendor: str
    name: str
    material: str
    colors: tuple
    archived: bool = False


def colors(value):
    if not isinstance(value, str):
        return ()
    result = []
    for part in value.split(',')[:8]:
        code = part.strip().lstrip('#').upper()
        if re.fullmatch(r'[0-9A-F]{6}([0-9A-F]{2})?', code):
            result.append(code[:6])
    return tuple(result)


def describe(raw):
    if not isinstance(raw, dict) or type(raw.get('id')) is not int or raw['id'] <= 0:
        raise ValueError('Invalid Spoolman spool')
    filament = raw.get('filament') or {}
    vendor = filament.get('vendor') or {}
    text = lambda value: str(value).strip()[:256] if value is not None else ''
    return Spool(raw['id'], text(vendor.get('name')) or 'Unknown',
                 text(filament.get('name')) or 'Unnamed',
                 text(filament.get('material')) or 'Unknown',
                 colors(filament.get('multi_color_hexes')) or colors(filament.get('color_hex')),
                 raw.get('archived') is True)


def tag_uid(raw):
    value = (raw.get('extra') or {}).get(TAG_FIELD)
    if value in (None, '', 'null', '""'):
        return None
    try:
        return normalize_uid(json.loads(value))
    except (ValueError, TypeError):
        # Never overwrite an unfamiliar existing field value.
        raise ValueError('Invalid Spoolman NFC ID')


@dataclass(frozen=True)
class BindingPlan:
    target: Spool
    uid: str
    previous_uid: str | None
    sources: tuple


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

    def assign(self, spool_id, uid, expected, approval=None):
        uid = normalize_uid(uid)
        raw, current = self.candidate(spool_id)
        if current != expected:
            raise ValueError('Spool changed; select again')
        previous_uid = tag_uid(raw)
        sources = []
        # Check every catalogue page, including archived spools, without
        # retaining the entire library. A conflicting UID is never moved.
        for offset in range(0, 10000, 100):
            rows = self.request('GET', '/v1/spool', query={
                'limit': 100, 'offset': offset, 'sort': 'id:asc',
                'allow_archived': 'true'})
            if not isinstance(rows, list) or len(rows) > 100:
                raise ValueError('Invalid Spoolman catalogue')
            for item in rows:
                if item.get('id') != spool_id and tag_uid(item) == uid:
                    sources.append(describe(item))
            if len(rows) < 100:
                break
        else:
            raise ValueError('Catalogue too large to check tag safely')
        plan = BindingPlan(expected, uid, previous_uid, tuple(sorted(sources, key=lambda s: s.id)))
        conflicting = bool(sources) or previous_uid not in (None, uid)
        if conflicting and approval != plan:
            # The second explicit confirmation must match freshly read data.
            raise BindingConflict(plan)
        fields = self.request('GET', '/v1/field/spool')
        if not isinstance(fields, list):
            raise ValueError('Invalid Spoolman fields')
        field = next((item for item in fields if item.get('key') == TAG_FIELD), None)
        if field is not None and field.get('field_type') != 'text':
            raise ValueError('Spoolman nfc_id must be a text field')
        if field is None:
            self.request('POST', '/v1/field/spool/' + TAG_FIELD,
                         body={'name': 'NFC ID', 'field_type': 'text'})
        # Re-read after conflict/schema checks; do not overwrite a changed spool.
        latest, fresh = self.candidate(spool_id)
        if fresh != expected or tag_uid(latest) != previous_uid:
            raise ValueError('Spool changed; select again')
        for source in plan.sources:
            owner = self.request('GET', '/v1/spool/%d' % source.id)
            if describe(owner) != source or tag_uid(owner) != uid:
                raise ValueError('Tag owner changed; select again')
        writing = False
        try:
            for source in plan.sources:
                writing = True
                cleared = self.request('PATCH', '/v1/spool/%d' % source.id,
                                       body={'extra': {TAG_FIELD: json.dumps('')}})
                if describe(cleared).id != source.id or tag_uid(cleared) is not None:
                    raise ValueError('Old tag removal not confirmed')
            if plan.sources:
                latest, fresh = self.candidate(spool_id)
                if fresh != expected or tag_uid(latest) != previous_uid:
                    raise ValueError('Target spool changed during move')
            # PATCH only our field; never replay an ambiguous server write.
            writing = True
            result = self.request('PATCH', '/v1/spool/%d' % spool_id,
                                 body={'extra': {TAG_FIELD: json.dumps(uid)}})
            if describe(result).id != spool_id or tag_uid(result) != uid:
                raise ValueError('Tag assignment not confirmed')
        except Exception as error:
            if plan.sources and writing:
                raise ValueError('Move incomplete; check Spoolman before retry') from error
            raise
        return uid
