"""Multi-channel notifications: in-app + email + FCM push + webhook.

One entry point for scenarios — ``notify(...)`` — fans a message out across an
always-on in-app record plus any of email / push / webhook, each configured
dynamically from the admin UI (secrets encrypted at rest) with ready Jinja2
templates.

Wire into a scenario app:

    from edge.core import create_app
    from edge.messaging import router as messaging_router
    app = create_app(registry, extra_routers=[messaging_router])

Send a notification from anywhere:

    from edge.messaging import notify
    await notify(
        db,
        user_ids=[user.id],
        title="Camera offline",
        body="Front-door camera stopped responding.",
        channels=["email", "push"],
        email_to=[user.email],
    )

The ORM models (``ChannelConfig``, ``DeviceToken``, ``Notification``) are exported
so ``Base.metadata`` includes their tables for creation/migration.
"""

from .config import ChannelConfig
from .dispatcher import notify
from .inapp import Notification
from .push import DeviceToken
from .router import router
from .template_store import EmailTemplate

__all__ = [
    "router",
    "notify",
    "ChannelConfig",
    "DeviceToken",
    "Notification",
    "EmailTemplate",
]
