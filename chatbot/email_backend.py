"""
chatbot/email_backend.py
========================
Custom Hybrid Email Backend for Zenbot.

Problem:
  Cloud providers like Render.com strictly BLOCK outbound SMTP ports
  (25, 465, and 587) on their Free tier to prevent spam abuse.
  Because of this, standard smtplib (smtp.gmail.com:587) hangs and times out
  on Render Free Web Services.

Solution:
  This backend checks for an HTTP API key:
  1. If BREVO_API_KEY is present: sends via Brevo REST API (HTTPS port 443).
     - Free 300 emails/day, no credit card required.
     - Works over standard HTTPS (port 443) which Render never blocks.
  2. If RESEND_API_KEY is present: sends via Resend REST API (HTTPS port 443).
     - Free 3,000 emails/month (100/day).
  3. Otherwise: falls back to standard Django SMTP (port 587) for local development.
"""
import base64
import json
import logging
import os
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend as SmtpBackend

logger = logging.getLogger(__name__)


class HybridEmailBackend(BaseEmailBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.smtp_backend = SmtpBackend(*args, **kwargs)

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        brevo_key = os.getenv("BREVO_API_KEY", "").strip()
        resend_key = os.getenv("RESEND_API_KEY", "").strip()

        if brevo_key:
            return self._send_via_brevo(email_messages, brevo_key)
        elif resend_key:
            return self._send_via_resend(email_messages, resend_key)
        else:
            return self.smtp_backend.send_messages(email_messages)

    def _send_via_brevo(self, messages, api_key: str) -> int:
        """Sends emails via Brevo transactional API over HTTPS (port 443)."""
        sent_count = 0
        sender_email = getattr(settings, "EMAIL_HOST_USER", "sharan2003murali@gmail.com")
        sender_name = getattr(settings, "COMPANY_NAME", "Zenbot Team")

        for msg in messages:
            try:
                # Extract HTML alternative if present
                html_body = ""
                for content, mimetype in getattr(msg, "alternatives", []):
                    if mimetype == "text/html":
                        html_body = content
                        break
                if not html_body:
                    html_body = f"<div style='font-family:sans-serif;'>{msg.body}</div>"

                payload = {
                    "sender": {"name": sender_name, "email": sender_email},
                    "to": [{"email": recipient} for recipient in msg.to],
                    "subject": msg.subject,
                    "htmlContent": html_body,
                    "textContent": msg.body or "",
                }

                # Encode attachments in Base64
                attachments = []
                for att in getattr(msg, "attachments", []):
                    if isinstance(att, tuple):
                        att_name, att_bytes, _ = att
                    else:
                        att_name = getattr(att, "name", "document.pdf")
                        att_bytes = getattr(att, "read", lambda: b"")()
                    if isinstance(att_bytes, str):
                        att_bytes = att_bytes.encode("utf-8")
                    attachments.append({
                        "name": att_name,
                        "content": base64.b64encode(att_bytes).decode("ascii"),
                    })

                if attachments:
                    payload["attachment"] = attachments

                req = urllib.request.Request(
                    "https://api.brevo.com/v3/smtp/email",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "api-key": api_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status in (200, 201, 202):
                        sent_count += 1
                        logger.info("Successfully sent email '%s' via Brevo HTTPS API to %s", msg.subject, msg.to)
            except Exception as exc:
                logger.error("Failed sending email via Brevo HTTPS API: %s", exc)
                if not self.fail_silently:
                    raise
        return sent_count

    def _send_via_resend(self, messages, api_key: str) -> int:
        """Sends emails via Resend API over HTTPS (port 443)."""
        sent_count = 0
        from_email = os.getenv("RESEND_FROM_EMAIL", "Zenbot <onboarding@resend.dev>")

        for msg in messages:
            try:
                html_body = ""
                for content, mimetype in getattr(msg, "alternatives", []):
                    if mimetype == "text/html":
                        html_body = content
                        break
                if not html_body:
                    html_body = f"<div>{msg.body}</div>"

                payload = {
                    "from": from_email,
                    "to": list(msg.to),
                    "subject": msg.subject,
                    "html": html_body,
                    "text": msg.body or "",
                }

                attachments = []
                for att in getattr(msg, "attachments", []):
                    if isinstance(att, tuple):
                        att_name, att_bytes, _ = att
                    else:
                        att_name = getattr(att, "name", "document.pdf")
                        att_bytes = getattr(att, "read", lambda: b"")()
                    if isinstance(att_bytes, str):
                        att_bytes = att_bytes.encode("utf-8")
                    attachments.append({
                        "filename": att_name,
                        "content": base64.b64encode(att_bytes).decode("ascii"),
                    })

                if attachments:
                    payload["attachments"] = attachments

                req = urllib.request.Request(
                    "https://api.resend.com/emails",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status in (200, 201, 202):
                        sent_count += 1
                        logger.info("Successfully sent email '%s' via Resend HTTPS API to %s", msg.subject, msg.to)
            except Exception as exc:
                logger.error("Failed sending email via Resend HTTPS API: %s", exc)
                if not self.fail_silently:
                    raise
        return sent_count
