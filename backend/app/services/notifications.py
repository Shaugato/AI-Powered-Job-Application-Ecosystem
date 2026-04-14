from __future__ import annotations

import json
import smtplib
import urllib.request
from email.message import EmailMessage

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.entities import IntegrationConnection, NotificationEvent, NotificationPreference


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def enqueue(self, *, channel: str, subject: str, body: str) -> NotificationEvent:
        event = NotificationEvent(channel=channel, subject=subject, body=body, delivery_status="queued")
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

        if channel == "slack":
            self._send_slack(event)
        elif channel == "email":
            self._send_email(event)
        elif channel == "dashboard":
            event.delivery_status = "stored"
            self.db.add(event)
            self.db.commit()
        return event

    def _preference_for(self, channel: str) -> NotificationPreference | None:
        return self.db.query(NotificationPreference).filter(NotificationPreference.channel == channel).first()

    def _connection_for(self, provider_key: str) -> IntegrationConnection | None:
        return (
            self.db.query(IntegrationConnection)
            .filter(IntegrationConnection.provider_key == provider_key, IntegrationConnection.status.in_(["configured", "connected"]))
            .order_by(IntegrationConnection.updated_at.desc())
            .first()
        )

    def _send_slack(self, event: NotificationEvent) -> None:
        preference = self._preference_for("slack")
        if preference is not None and not preference.enabled:
            event.delivery_status = "disabled"
            self.db.add(event)
            self.db.commit()
            return

        webhook_url = self.settings.slack_webhook_url
        connection = self._connection_for("slack_webhook")
        if connection is not None:
            webhook_url = str((connection.secrets_json or {}).get("webhook_url") or webhook_url or "")
        if not webhook_url:
            event.delivery_status = "pending_config"
            self.db.add(event)
            self.db.commit()
            return
        payload = json.dumps({"text": f"*{event.subject}*\n{event.body}"}).encode("utf-8")
        request = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10):  # pragma: no cover
            event.delivery_status = "sent"
            self.db.add(event)
            self.db.commit()

    def _send_email(self, event: NotificationEvent) -> None:
        preference = self._preference_for("email")
        if preference is not None and not preference.enabled:
            event.delivery_status = "disabled"
            self.db.add(event)
            self.db.commit()
            return

        smtp_host = self.settings.smtp_host
        smtp_port = self.settings.smtp_port
        smtp_username = self.settings.smtp_username
        smtp_password = self.settings.smtp_password
        from_email = self.settings.email_from or self.settings.smtp_username

        connection = self._connection_for("smtp")
        if connection is not None:
            settings_json = connection.settings_json or {}
            secrets_json = connection.secrets_json or {}
            smtp_host = str(settings_json.get("host") or smtp_host or "")
            smtp_port = int(settings_json.get("port") or smtp_port or 587)
            smtp_username = str(settings_json.get("username") or smtp_username or "")
            smtp_password = str(secrets_json.get("password") or smtp_password or "")
            from_email = str(settings_json.get("from_email") or from_email or smtp_username or "")

        recipient = preference.target if preference and preference.target else smtp_username
        if not recipient or not smtp_host or not smtp_username or not smtp_password:
            event.delivery_status = "pending_config"
            self.db.add(event)
            self.db.commit()
            return

        message = EmailMessage()
        message["From"] = from_email or smtp_username
        message["To"] = recipient
        message["Subject"] = event.subject
        message.set_content(event.body)

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:  # pragma: no cover
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(message)
            event.delivery_status = "sent"
            self.db.add(event)
            self.db.commit()
