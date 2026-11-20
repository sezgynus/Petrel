"""Notification record for the Petrel updater's confirmed availability."""
from petrel.features.notifications.store import Notification, Persistence, Retention


UPDATE_AVAILABLE = Notification(
    source='software_update',
    key='petrel',
    title='Petrel update available',
    detail='Open Info to review',
    action='open_petrel_update',
    retention=Retention.UNTIL_RESOLVED,
    persistence=Persistence.PERSISTENT,
)
