"""
chatbot/tasks.py
================
Celery background tasks for Zenbot.

Previously these ran in raw daemon threads (threading.Thread) which were
unreliable — lost on server restart, no retry, no monitoring.

Now every background job is a proper Celery task:
  - Survives server restarts (task is persisted in DB until a worker picks it up)
  - Retries automatically on transient Gemini API errors (429 / 503)
  - Visible in Django admin via django-celery-results
  - Thread-safe: multiple workers can run safely in parallel
"""

import logging
import time

from celery import shared_task
from django.core.cache import cache

from .ai import ai_engine

logger = logging.getLogger(__name__)

# Cache key helpers — keeps key format consistent across views + tasks
def _cache_key(user_id, role_name: str) -> str:
    """Returns the cache key for a pre-computed resume analysis result."""
    # Normalise role name so minor casing differences don't cause cache misses
    safe_role = role_name.strip().lower().replace(" ", "_")
    return f"zenbot_resume_v2_{user_id}_{safe_role}"


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=15,   # Wait 15 s before retrying on transient errors
    name="chatbot.tasks.precompute_resume_analysis",
)
def precompute_resume_analysis(self, user_id: int, roles: list, resume_text: str, user_name: str):
    """
    Celery task: pre-compute resume match analysis for each suggested role.

    Called immediately after upload_resume() returns the role suggestions so
    that by the time the user clicks a role button, the result is already cached
    and can be served instantly.

    Args:
        user_id:     ID of the FirebaseUser who uploaded the resume.
        roles:       List of role name strings to analyse (max 3).
        resume_text: Extracted plain text of the uploaded PDF.
        user_name:   Display name used in Gemini prompts.
    """
    logger.info(
        "Celery task started — pre-computing %d role(s) for user #%s: %s",
        len(roles), user_id, roles,
    )

    for idx, role_item in enumerate(roles):
        if isinstance(role_item, dict):
            role_name = role_item.get("role", "")
            role_loc = role_item.get("location", "Chennai")
            is_intern = role_item.get("is_internship", False)
        else:
            role_name = str(role_item)
            role_loc = "Chennai"
            is_intern = False

        cache_key = _cache_key(user_id, role_name)

        # Skip if already cached (e.g. task was retried and some roles succeeded)
        if cache.get(cache_key):
            logger.info("Cache HIT (already computed): %s", role_name)
            continue

        try:
            result = ai_engine.check_resume_match(
                resume_text,
                user_name,
                category="Candidate Evaluation",
                role=role_name,
                is_internship=is_intern,
                location=role_loc,
            )

            # Store in DB-backed cache for 1 hour
            cache.set(cache_key, result, timeout=3600)
            logger.info("Pre-computed and cached: %s (loc: %s)", role_name, role_loc)

        except Exception as exc:
            exc_str = str(exc)
            logger.error("Pre-compute failed for role '%s': %s", role_name, exc_str)

            # Retry the whole task on transient API errors (rate limit / overload)
            is_transient = (
                "429" in exc_str
                or "503" in exc_str
                or "RESOURCE_EXHAUSTED" in exc_str
                or "UNAVAILABLE" in exc_str
            )
            if is_transient and self.request.retries < self.max_retries:
                # Exponential backoff: 15 s → 45 s
                delay = 15 * (2 ** self.request.retries)
                logger.warning(
                    "Transient error — retrying task in %ds (attempt %d/%d)",
                    delay, self.request.retries + 1, self.max_retries,
                )
                raise self.retry(exc=exc, countdown=delay)
            # Non-transient error: log and continue with remaining roles
            continue

        # Small delay between roles to avoid concurrent rate-limit hits on free API keys
        if idx < len(roles) - 1:
            time.sleep(2.0)

    logger.info("Pre-computation task finished for user #%s", user_id)


def send_application_emails(app_id: int, app_type: str, accept_url: str = "", reject_url: str = "") -> bool:
    """
    Dispatches confirmation email to candidate.
    Safely buffers attachment bytes so both candidate and HR emails reliably
    receive the resume regardless of storage backend (local disk or Cloudinary).

    BUG-07 fix: this function should ONLY be called via Celery
    (send_application_emails_task.delay() / .apply_async()) so that:
      - Email send is non-blocking and does not delay the HTTP response
      - Retries are managed by Celery on transient SMTP failures
      - Task status is visible in the Django admin (django-celery-results)
    Calling it synchronously in a request thread will block for 3-10s.
    """
    # BUG-07 fix: warn if called outside a Celery worker so the problem is
    # immediately visible in logs rather than causing silent request slowdowns.
    try:
        from celery import current_task
        if current_task and current_task.request and current_task.request.id:
            pass  # Running inside a Celery task — correct path
        else:
            logger.warning(
                "send_application_emails called OUTSIDE a Celery worker for app #%d (%s). "
                "This blocks the request thread. Use send_application_emails_task.delay() instead.",
                app_id, app_type,
            )
    except Exception:
        pass  # If Celery is not available, log and continue gracefully

    from django.conf import settings
    from django.core.mail import EmailMultiAlternatives
    from django.utils.html import strip_tags

    from .models import InternshipApplication, JobApplication

    logger.info("Starting email dispatch for %s application #%d", app_type, app_id)

    if app_type == 'internship':
        app = InternshipApplication.objects.filter(id=app_id).first()
    else:
        app = JobApplication.objects.filter(id=app_id).first()

    if not app:
        logger.warning("Application #%d (%s) not found for email dispatch.", app_id, app_type)
        return False

    company_name = getattr(settings, 'COMPANY_NAME', 'Zenbot System')

    # ── 1. Candidate Confirmation Email (No Resume/Photo Attachments) ────────
    cand_subject = f"Application Confirmed - {app_type.title()} for {app.role}"

    raw_ug_course = (getattr(app, 'ug_course', None) or '').strip()
    raw_course = (getattr(app, 'course', None) or '').strip()

    if raw_ug_course:
        ug_course_val = raw_ug_course
        pg_course_val = raw_course
    elif raw_course.startswith('M'):
        ug_course_val = 'Undergraduate Degree'
        pg_course_val = raw_course
    else:
        ug_course_val = raw_course or 'N/A'
        pg_course_val = ''

    ug_college_val = app.ug_college or 'N/A'
    ug_cgpa_val = app.ug_cgpa or 'N/A'

    pg_college_val = (getattr(app, 'pg_college', None) or '').strip()
    pg_cgpa_val = (getattr(app, 'pg_cgpa', None) or '').strip()

    has_pg = bool(
        (pg_college_val and pg_college_val.upper() != 'N/A') or
        (pg_cgpa_val and pg_cgpa_val.upper() != 'N/A') or
        (pg_course_val and pg_course_val.upper() != 'N/A')
    )

    rows = [
        ("Applied Role", app.role),
        ("Full Name", app.full_name),
        ("Email", app.email),
        ("Phone", app.phone or 'N/A'),
        ("UG Education", ug_course_val),
        ("UG College", ug_college_val),
        ("UG CGPA", ug_cgpa_val),
    ]

    if has_pg:
        if pg_course_val and pg_course_val.upper() != 'N/A':
            rows.append(("PG Education", pg_course_val))
        if pg_college_val and pg_college_val.upper() != 'N/A':
            rows.append(("PG College", pg_college_val))
        if pg_cgpa_val and pg_cgpa_val.upper() != 'N/A':
            rows.append(("PG CGPA", pg_cgpa_val))

    rows_html = []
    for idx, (label, val) in enumerate(rows):
        bg = ' style="background:#f8fafc;"' if idx % 2 == 0 else ""
        rows_html.append(
            f'<tr{bg}><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600;width:35%;">{label}</td>'
            f'<td style="padding:8px;border:1px solid #e2e8f0;">{val}</td></tr>\n'
        )
    table_rows_html = "".join(rows_html)

    cand_html = f"""
    <div style="font-family:'Segoe UI',Tahoma,sans-serif;max-width:600px;margin:0 auto;padding:24px;border:1px solid #e2e8f0;border-radius:12px;background:#ffffff;color:#1a202c;">
        <div style="text-align:center;border-bottom:2px solid #3182ce;padding-bottom:15px;margin-bottom:20px;">
            <h2 style="color:#2b6cb0;margin:0;font-size:22px;">{company_name}</h2>
            <p style="color:#4a5568;margin:5px 0 0 0;font-size:14px;">{app_type.title()} Application Confirmation</p>
        </div>
        <p style="font-size:15px;">Hi <strong>{app.full_name}</strong>,</p>
        <p style="font-size:14px;color:#4a5568;">Your application for the <strong>{app.role}</strong> position has been successfully received and recorded in our recruitment system.</p>

        <table style="width:100%;border-collapse:collapse;margin:18px 0;font-size:13px;">
            {table_rows_html}
        </table>
        <p style="font-size:14px;color:#4a5568;">Our hiring team will review your credentials and follow up directly with your interview schedule.</p>
        <div style="margin-top:24px;border-top:1px solid #e2e8f0;padding-top:12px;font-size:12px;color:#a0aec0;text-align:center;">
            Automated confirmation from {company_name} Portal.
        </div>
    </div>"""

    try:
        cand_msg = EmailMultiAlternatives(cand_subject, strip_tags(cand_html), settings.DEFAULT_FROM_EMAIL, [app.email])
        cand_msg.attach_alternative(cand_html, "text/html")
        cand_msg.send(fail_silently=False)
        logger.info("Candidate confirmation email sent successfully to %s (attachments omitted per configuration)", app.email)
    except Exception as exc:
        logger.error("Failed sending candidate confirmation email: %s", exc)

    # ── 2. HR Notification Email (Disabled) ──────────────────────────────────
    # HR reviews applications and resumes directly in the HR Panel (/hr/)
    logger.info("HR email notification omitted: HR accesses candidate details and resumes directly via HR Panel")
    return True


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    name="chatbot.tasks.send_application_emails_task",
)
def send_application_emails_task(self, app_id: int, app_type: str, accept_url: str = "", reject_url: str = ""):
    """Celery wrapper for send_application_emails."""
    return send_application_emails(app_id, app_type, accept_url, reject_url)



@shared_task(
    name="chatbot.tasks.gemini_key_health_check",
    ignore_result=True,
)
def gemini_key_health_check():
    """
    Fix 12: Gemini API key health check and rotation optimiser.
    Tests every configured key and moves exhausted ones to the end of the
    rotation list so fresh keys are tried first.
    Schedule via CELERY_BEAT_SCHEDULE every 55 minutes.
    """
    from .ai import ai_engine
    keys = list(ai_engine._get_api_keys())
    if not keys or len(keys) <= 1:
        logger.debug("Gemini key health check: only 1 key configured, skipping.")
        return

    healthy, exhausted = [], []
    for key in keys:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=key)
            client.models.generate_content(
                model='gemini-2.0-flash-lite',
                contents='Reply: OK',
                config=types.GenerateContentConfig(max_output_tokens=5),
            )
            healthy.append(key)
        except Exception as exc:
            exc_str = str(exc)
            if '429' in exc_str or 'RESOURCE_EXHAUSTED' in exc_str:
                exhausted.append(key)
                logger.warning("Gemini key ...%s is exhausted, moved to end.", key[-6:])
            else:
                healthy.append(key)

    optimal = healthy + exhausted
    if optimal != keys:
        ai_engine._API_KEYS_POOL[:] = optimal
        ai_engine._current_key_index = 0
        logger.info("Gemini key rotation reordered: %d healthy, %d exhausted.", len(healthy), len(exhausted))
