"""Persistent notifications for the active service cycle of a care plan."""
import json

from petrel.features.maintenance.records.care import task_label
from petrel.features.maintenance.ui.experience import device_name
from petrel.features.notifications.store import Notification, Retention


SOURCE = 'maintenance'
ACTION = 'open_due_maintenance_plan'


def care_notification_key(policy, last):
    anchor = None if not last else last.get('timestamp', last.get('_tracking_started_at'))
    return json.dumps((policy.device, policy.task_id, policy.basis, anchor),
                      ensure_ascii=False, separators=(',', ':'))


def reconcile_care_notifications(store, plans, due_state):
    """An unknown counter must not clear an already-due service cycle."""
    active = set()
    for policy, last, cached in plans:
        key = care_notification_key(policy, last)
        state = due_state(policy, last, cached)
        if state != 'not_due':
            active.add(key)
        if state == 'due':
            store.publish(Notification(
                source=SOURCE, key=key, title='Maintenance due',
                detail=f'{device_name(policy.device)} / {task_label(policy.task_id, policy.device)}',
                action=ACTION, retention=Retention.UNTIL_RESOLVED,
            ))
    for item in store.snapshot()[1]:
        if item.source == SOURCE and item.key not in active:
            store.resolve(*item.identity)
