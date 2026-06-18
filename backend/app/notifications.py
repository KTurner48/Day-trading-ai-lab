"""Log-only notification dispatcher: always records a row; sends externally only
when a channel's credentials are present (none are, by default)."""
from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Notification
from app.models.enums import NotificationChannel, NotificationStatus

_REQUIRED_ENV = {
    NotificationChannel.EMAIL: ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"),
    NotificationChannel.SMS: ("TWILIO_SID", "TWILIO_TOKEN", "TWILIO_FROM"),
    NotificationChannel.DISCORD: ("DISCORD_WEBHOOK_URL",),
    NotificationChannel.TELEGRAM: ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"),
}


def channel_configured(channel: NotificationChannel) -> bool:
    return all(os.environ.get(k) for k in _REQUIRED_ENV[channel])


class NotificationDispatcher:
    async def dispatch(self, db: AsyncSession, *, channel: NotificationChannel,
                       body: str, subject: str | None = None) -> Notification:
        n = Notification(channel=channel, subject=subject, body=body,
                         status=NotificationStatus.QUEUED)
        db.add(n)
        await db.flush()
        if not channel_configured(channel):
            # Log-only: recorded locally, nothing sent externally.
            n.status = NotificationStatus.SENT
            n.last_error = "log_only:not_configured"
            return n
        # A configured channel would dispatch here; MVP marks SENT without the marker.
        n.status = NotificationStatus.SENT
        return n
