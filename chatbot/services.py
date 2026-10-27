"""
chatbot/services.py
===================
Business-logic helpers extracted from views.py to keep views thin and testable.
"""

import datetime
import logging

from django.conf import settings
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

logger = logging.getLogger(__name__)


# ── 1. Strict Rate Throttle for application-submission endpoints ───────────────


class ApplicationSubmitUserThrottle(UserRateThrottle):
    """5 submissions per minute per authenticated user."""
    scope = 'application_submit'


class ApplicationSubmitAnonThrottle(AnonRateThrottle):
    """2 submissions per minute per IP for anonymous callers."""
    scope = 'application_submit_anon'


# Disadvantage #4 fix: explicit chat throttles to prevent Gemini quota exhaustion.
# Authenticated users: 20 messages/minute. Unauthenticated IPs: 5/minute.
class ChatRateThrottle(UserRateThrottle):
    """20 chat messages per minute per authenticated user."""
    scope = 'chat'


class ChatAnonRateThrottle(AnonRateThrottle):
    """5 chat messages per minute per anonymous IP (SSE endpoint fallback)."""
    scope = 'chat_anon'



# ── 2. Multi-HR Email Support ─────────────────────────────────────────────────

def get_hr_emails() -> list:
    """
    Returns list of HR email addresses from settings.HR_EMAIL.
    Supports comma-separated values: 'hr1@company.com, hr2@company.com'.
    """
    import re
    raw = getattr(settings, 'HR_EMAIL', '') or ''
    if isinstance(raw, (list, tuple)):
        emails = [str(e).strip().lower() for e in raw if str(e).strip()]
    else:
        emails = [e.strip().lower() for e in str(raw).split(',') if e.strip()]
    if not emails:
        fallback = getattr(settings, 'DEFAULT_FROM_EMAIL', '')
        m = re.search(r'[\w.\-+]+@[\w.\-]+', str(fallback))
        emails = [m.group(0)] if m else []
    return emails


def is_hr_email(email: str) -> bool:
    """Returns True if email is in the configured HR email list (case-insensitive)."""
    return email.strip().lower() in get_hr_emails()


# ── 3. HR Audit Log Helper ────────────────────────────────────────────────────

def audit_hr_action(actor_email, action, target_type='', target_id=None, detail=''):
    """
    Write a single HRAuditLog row. Swallows exceptions so audit logging
    never breaks the main request flow.
    """
    try:
        from .models import HRAuditLog
        HRAuditLog.objects.create(
            actor_email=actor_email,
            action=action,
            target_type=target_type or '',
            target_id=target_id,
            detail=detail or '',
        )
    except Exception as exc:
        logger.warning("audit_hr_action failed (non-critical): %s", exc)


# ── 4. Interview Time Resolver ─────────────────────────────────────────────────

_GENERIC_PLACEHOLDERS = [
    'upcoming business days', 'coordinated by hr', 'coordinated shortly',
    'will confirm', 'exact time coordinated', 'to be determined', 'tbd',
]


def resolve_interview_time(time_text):
    """Normalises a scheduled_time string. Replaces placeholders with a concrete date."""
    from .email_utils import get_default_interview_schedule
    if not time_text:
        return get_default_interview_schedule()
    if any(p in time_text.lower() for p in _GENERIC_PLACEHOLDERS):
        return get_default_interview_schedule()
    return time_text


# ── 5. RFC-5545 .ics Calendar Builder ─────────────────────────────────────────

def build_ics_calendar(uid, summary, description, location, scheduled_time,
                       duration_hours=2, organizer_name=''):
    """
    Returns a standards-compliant iCalendar (.ics) string with DTSTART/DTEND.
    """
    now_stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    dtstart = now_stamp
    dtend = now_stamp
    try:
        dt_str = scheduled_time.replace(' IST', '').strip() if scheduled_time else ''
        if dt_str:
            dt_obj = datetime.datetime.strptime(dt_str, '%d %b %Y, %I:%M %p').replace(tzinfo=datetime.timezone.utc)
            dtstart = dt_obj.strftime('%Y%m%dT%H%M%S')
            dtend = (dt_obj + datetime.timedelta(hours=duration_hours)).strftime('%Y%m%dT%H%M%S')
    except (ValueError, TypeError):
        pass

    org = organizer_name or getattr(settings, 'COMPANY_NAME', 'Zenbot')
    safe_desc = description.replace('\n', '\\n').replace('\r', '')

    # BUG-05 fix: anchor time to IST timezone so all calendar apps show correct local time
    # Use TZID=Asia/Kolkata when we have a parsed local time; fall back to UTC stamp otherwise
    if dtstart != now_stamp:
        dtstart_line = f'DTSTART;TZID=Asia/Kolkata:{dtstart}'
        dtend_line   = f'DTEND;TZID=Asia/Kolkata:{dtend}'
    else:
        dtstart_line = f'DTSTART:{dtstart}'
        dtend_line   = f'DTEND:{dtend}'

    lines = [
        'BEGIN:VCALENDAR', 'VERSION:2.0',
        f'PRODID:-//{org}//Zenbot//EN', 'METHOD:REQUEST',
        'BEGIN:VEVENT',
        f'UID:{uid}', f'DTSTAMP:{now_stamp}',
        dtstart_line, dtend_line,
        f'SUMMARY:{summary}', f'DESCRIPTION:{safe_desc}',
        f'LOCATION:{location or "Company Campus"}',
        'STATUS:CONFIRMED', 'END:VEVENT', 'END:VCALENDAR',
    ]
    return '\r\n'.join(lines) + '\r\n'


# ── 6. Honeypot check ─────────────────────────────────────────────────────────

HONEYPOT_FIELD = 'website'


def check_honeypot(data):
    """Returns True (is spam) if the hidden honeypot field is filled."""
    return bool(data.get(HONEYPOT_FIELD, '').strip())
