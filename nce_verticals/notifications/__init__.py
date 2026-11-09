"""nce_verticals.notifications — C13 Notifications and Reminders vertical module."""

from __future__ import annotations

from nce_verticals.notifications.models import (
    NotificationRecord,
    NotificationSubscription,
    ReminderRecord,
)
from nce_verticals.notifications.reminders import (
    create_reminder,
    fire_pending_reminders,
)
from nce_verticals.notifications.resources import (
    NOTIFICATION_SPEC,
    REMINDER_SPEC,
)
from nce_verticals.notifications.service import (
    create_notification,
    get_subscribed_principals,
    subscribe_principal,
)
from nce_verticals.notifications.subscribers import (
    register_notifications_subscribers,
)

__all__ = [
    "NotificationRecord",
    "ReminderRecord",
    "NotificationSubscription",
    "create_notification",
    "subscribe_principal",
    "get_subscribed_principals",
    "create_reminder",
    "fire_pending_reminders",
    "register_notifications_subscribers",
    "NOTIFICATION_SPEC",
    "REMINDER_SPEC",
]
