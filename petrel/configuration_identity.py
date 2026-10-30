"""Canonical identities for frozen Klipper configuration and persisted evidence."""
from collections.abc import Mapping
import hashlib
import json


def _plain(value):
    if isinstance(value, Mapping):
        return {key:_plain(item) for key,item in value.items()}
    if isinstance(value, (tuple,list)):
        return [_plain(item) for item in value]
    return value


def stable_digest(value):
    raw=json.dumps(_plain(value),sort_keys=True,allow_nan=False,separators=(',',':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def legacy_digest(value):
    """Read compatibility only: exact old representation, never a new identity."""
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()
