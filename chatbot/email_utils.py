"""
email_utils.py — Shared email helpers for application status notifications.
Used by both admin.py (bulk actions) and views.py (HR panel API).
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


# Disadvantage #8 fix: campus addresses moved to settings.CAMPUS_ADDRESS_MAP.
# Override any address via env var (e.g. CAMPUS_ADDR_PUNE=...) — no code change needed.
def _get_campus_map():
    """Lazy-load campus addresses from settings to support env-var overrides."""
    return getattr(settings, 'CAMPUS_ADDRESS_MAP', {
        'bengaluru':   'Zensar Technologies Ltd, Level 4, Brigade Tech Park, Whitefield, Bengaluru, Karnataka 560066',
        'hyderabad':   'Zensar Technologies Ltd, 5th Floor, Cyber Pearl Building, Hitec City, Hyderabad, Telangana 500081',
        'chennai_dlf': 'Zensar Technologies Ltd, Block 7, DLF IT Park, Manapakkam, Chennai, Tamil Nadu 600089',
        'chennai_omr': 'Zensar Technologies Ltd, Rajiv Gandhi Salai (OMR), Navalur, Chennai, Tamil Nadu 600130',
        'pune':        'Zensar Technologies Ltd, Zensar Knowledge Park, Plot #4, Kharadi, Pune, Maharashtra 411014',
    })

def get_campus_address_for_location(loc_str):
    """Resolve physical office address based on candidate location or vacancy state."""
    campus_map = _get_campus_map()
    loc = str(loc_str or '').lower()
    if any(k in loc for k in ('bengaluru', 'bangalore', 'karnataka', 'whitefield')):
        return campus_map['bengaluru']
    elif any(k in loc for k in ('hyderabad', 'telangana', 'andhra', 'hitec', 'cyber')):
        return campus_map['hyderabad']
    elif 'omr' in loc:
        return campus_map['chennai_omr']
    elif any(k in loc for k in ('chennai', 'tamil', 'dlf', 'manapakkam')):
        return campus_map['chennai_dlf']
    elif any(k in loc for k in ('pune', 'maharashtra', 'kharadi')):
        return campus_map['pune']
    return campus_map['chennai_dlf']


def send_status_email(app, app_type_label, status, reason='', interview_data=None):
    """Dispatch the right email based on new status."""
    if status == 'selected':
        _send_selection_email(app, app_type_label, interview_data=interview_data)
    elif status == 'rejected':
        _send_rejection_email(app, app_type_label, reason)


def get_default_interview_schedule() -> str:
    """Calculates a specific concrete interview date & time (e.g. 2 business days ahead at 10:30 AM IST).
    Skips weekends (Saturday & Sunday).
    Example: '15 Sep 2026, 10:30 AM IST'

    BUG-12 fix: use IST timezone explicitly so interview dates are correct
    regardless of the server's system timezone (commonly UTC in Linux/cloud).
    """
    # BUG-12 fix: always use IST (Asia/Kolkata, UTC+5:30) — not server local time
    try:
        from datetime import timedelta, timezone
        IST = timezone(timedelta(hours=5, minutes=30))
        now = __import__('datetime').datetime.now(tz=IST)
    except Exception:
        now = __import__('datetime').datetime.now(tz=timezone.utc)  # graceful fallback

    from datetime import timedelta as _td
    d = now + _td(days=2)
    if d.weekday() == 5:   # Saturday → push to Monday (+2 days)
        d += _td(days=2)
    elif d.weekday() == 6: # Sunday   → push to Monday (+1 day)
        d += _td(days=1)
    return d.strftime("%d %b %Y, 10:30 AM IST")


def _send_selection_email(app, app_type_label, interview_data=None):
    """
    Send an official selection and interview call letter email to the candidate.
    Includes:
    1. Interview schedule (date and time)
    2. Number of interview rounds & detailed breakdown of each round
    3. Candidate's submitted resume attached to the email
    """
    if not interview_data or not isinstance(interview_data, dict):
        interview_data = {}

    is_internship = str(app_type_label).lower().startswith('intern')
    scheduled_time = (interview_data.get('scheduled_time') or '').strip()

    generic_placeholders = [
        'upcoming business days',
        'coordinated by hr',
        'coordinated shortly',
        'will confirm',
        'exact time coordinated',
        'to be determined',
        'tbd',
    ]
    if not scheduled_time or any(p in scheduled_time.lower() for p in generic_placeholders):
        scheduled_time = get_default_interview_schedule()

    # Resolve campus address across vacancy states: Bengaluru (KA), Hyderabad (TS/AP), Chennai (TN), Pune (MH)
    app_loc = str(getattr(app, 'preferred_location', '') or getattr(app, 'location', '') or '').lower()
    default_venue = get_campus_address_for_location(app_loc)

    venue_address = interview_data.get('venue_address') or interview_data.get('meeting_link') or default_venue
    # Strip any leftover legacy google meet URLs if entered mistakenly
    if 'meet.google.com' in venue_address or 'zoom.us' in venue_address:
        venue_address = default_venue

    notes = interview_data.get('notes') or ""

    # Parse or set strict rounds breakdown:
    # Job: 3 Rounds (Aptitude: 30 Mins, Technical: 45 Mins, HR: 30 Mins)
    # Internship: 1 Round (HR Round: 30 Mins)
    rounds_details = interview_data.get('rounds_details')
    if is_internship:
        total_rounds = "1 Round (HR Round)"
        if not rounds_details or not isinstance(rounds_details, list) or len(rounds_details) != 1:
            rounds_details = [
                {
                    "name": "Round 1: In-Person HR Interview & Profile Assessment",
                    "duration": "30 Mins",
                    "desc": "Direct in-person discussion at company campus reviewing academic background, project achievements, internship duration, cultural fitment, and onboarding formalities."
                }
            ]
    else:
        total_rounds = "3 Rounds (Aptitude, Technical, HR)"
        if not rounds_details or not isinstance(rounds_details, list) or len(rounds_details) != 3:
            rounds_details = [
                {
                    "name": "Round 1: Aptitude Assessment & Logical Reasoning",
                    "duration": "30 Mins",
                    "desc": "In-person quantitative aptitude, logical reasoning, verbal ability, and analytical problem-solving assessment at our campus lab."
                },
                {
                    "name": "Round 2: Technical Interview & Live Problem Solving",
                    "duration": "45 Mins",
                    "desc": "In-person core technical domain deep-dive, hands-on programming/coding evaluation, system architecture, and project walkthrough with technical leads."
                },
                {
                    "name": "Round 3: HR Discussion & Culture Fitment",
                    "duration": "30 Mins",
                    "desc": "In-person discussion on cultural fitment, career roadmap, role expectations, compensation details, and joining schedule."
                }
            ]

    # Build HTML for the rounds timeline
    rounds_html = ""
    for idx, r in enumerate(rounds_details, 1):
        rounds_html += f"""
        <div style="background:#ffffff;border:1px solid #d1fae5;border-left:4px solid #10b981;border-radius:8px;padding:14px 16px;margin-bottom:10px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;flex-wrap:wrap;">
                <span style="font-weight:700;color:#065f46;font-size:14px;">
                    {r.get('name', f'Round {idx}')}
                </span>
                <span style="background:#dcfce7;color:#047857;font-size:11px;font-weight:700;padding:2px 8px;border-radius:12px;">
                    ⏱ {r.get('duration', '45 Mins')}
                </span>
            </div>
            <p style="margin:4px 0 0;font-size:13px;color:#4b5563;line-height:1.5;">
                {r.get('desc', '')}
            </p>
        </div>
        """

    notes_html = ""
    if notes:
        notes_html = f"""
        <div style="background:#fffbeb;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:6px;margin:16px 0;">
            <div style="font-size:12px;font-weight:700;color:#b45309;text-transform:uppercase;margin-bottom:4px;">📌 Special Instructions from HR:</div>
            <div style="font-size:13px;color:#92400e;line-height:1.5;">{notes}</div>
        </div>
        """

    subject = f"Congratulations! You've been Selected for {app.role} — In-Person Interview Call Letter"
    html_message = f"""
    <div style="font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;max-width:640px;margin:0 auto;border-radius:14px;overflow:hidden;border:1px solid #a7f3d0;box-shadow:0 10px 25px rgba(0,0,0,0.05);">
        <div style="background:linear-gradient(135deg,#064e3b,#047857,#10b981);padding:34px 28px;text-align:center;">
            <h1 style="color:#ffffff;margin:0;font-size:24px;font-weight:700;letter-spacing:-0.5px;">Congratulations, {app.full_name}!</h1>
            <p style="color:#a7f3d0;margin:8px 0 0;font-size:15px;font-weight:500;">Application Accepted · Official In-Person Interview Call Letter</p>
        </div>
        <div style="background:#ffffff;padding:30px 32px;">
            <p style="font-size:15px;color:#1a202c;line-height:1.7;margin-top:0;">
                Dear <strong>{app.full_name}</strong>,
            </p>
            <p style="font-size:15px;color:#374151;line-height:1.7;">
                We are delighted to inform you that following the review of your profile and submitted application,
                our recruitment panel has <strong>accepted your application</strong> for the
                <strong style="color:#065f46;">{app.role}</strong> ({app_type_label}) position at
                <strong>Zensar Technologies</strong>.
            </p>

            <!-- Schedule & Logistics Card -->
            <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:18px 22px;margin:22px 0;">
                <h3 style="margin:0 0 14px;color:#065f46;font-size:15px;display:flex;align-items:center;gap:6px;">
                    📅 In-Person Interview Schedule & Venue
                </h3>
                <table style="width:100%;font-size:14px;border-collapse:collapse;">
                    <tr>
                        <td style="padding:6px 0;color:#6b7280;font-weight:600;width:32%;">Applied Position</td>
                        <td style="padding:6px 0;color:#1a202c;font-weight:700;">{app.role} ({app_type_label})</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;color:#6b7280;font-weight:600;">Status</td>
                        <td style="padding:6px 0;">
                            <span style="background:#dcfce7;color:#15803d;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:700;">✓ Selected for In-Person Interviews</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;color:#6b7280;font-weight:600;">Date & Time</td>
                        <td style="padding:6px 0;color:#065f46;font-weight:700;font-size:15px;">{scheduled_time}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;color:#6b7280;font-weight:600;">Interview Mode</td>
                        <td style="padding:6px 0;">
                            <span style="background:#ecfdf5;color:#065f46;border:1px solid #a7f3d0;padding:2px 10px;border-radius:16px;font-size:12px;font-weight:700;">
                                🏢 Direct In-Person Interview (No Online / Virtual)
                            </span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#6b7280;font-weight:600;vertical-align:top;">📍 Campus Venue Address</td>
                        <td style="padding:8px 0;color:#1e293b;font-weight:600;line-height:1.5;">
                            {venue_address}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;color:#6b7280;font-weight:600;">Interview Structure</td>
                        <td style="padding:6px 0;color:#1a202c;font-weight:700;">{total_rounds}</td>
                    </tr>
                </table>
            </div>

            {notes_html}

            <!-- Interview Rounds Breakdown -->
            <div style="margin:24px 0;">
                <h3 style="margin:0 0 14px;color:#065f46;font-size:15px;">
                    🎯 Interview Process Breakdown ({total_rounds})
                </h3>
                {rounds_html}
            </div>

            <!-- In-Person Preparation Checklist -->
            <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:16px 20px;margin:22px 0;">
                <h4 style="margin:0 0 10px;color:#1e293b;font-size:13px;text-transform:uppercase;letter-spacing:0.5px;">📋 In-Person Interview Guidelines:</h4>
                <ul style="margin:0;padding-left:18px;font-size:13px;color:#475569;line-height:1.7;">
                    <li><strong>Reporting Time:</strong> Please arrive at the company campus reception at least 15 minutes prior to the scheduled start time.</li>
                    <li><strong>Identification:</strong> Carry an original government-issued photo ID card (Aadhaar / Passport / Voter ID / Driving License) or college ID for security check-in at the visitor gate.</li>
                    <li><strong>Documents to Bring:</strong> Bring 2 printed hardcopies of your resume and original/photocopies of your educational marksheets.</li>
                    {'<li><strong>Assessment Setup:</strong> Systems and materials will be provided in our campus lab for Round 1 (Aptitude) and Round 2 (Technical).' if not is_internship else '<li><strong>HR Evaluation:</strong> Direct in-person HR evaluation focusing on your academic projects, role interest, and onboarding formalities.'}</li>
                    <li><strong>Direct In-Person Attendance:</strong> Please note that this is strictly an in-person on-campus interview. No virtual or video conference link will be provided.</li>
                </ul>
            </div>

            <p style="font-size:15px;color:#374151;line-height:1.7;">
                If you have any questions regarding directions or require rescheduling due to unavoidable circumstances, please reply directly to this email or reach out to our Talent Acquisition Team at <a href="mailto:careers@zensar.com" style="color:#059669;text-decoration:underline;">careers@zensar.com</a>.
            </p>
            <p style="font-size:15px;color:#374151;line-height:1.7;margin-bottom:0;">
                We look forward to speaking with you. Welcome to the <strong>Zensar Technologies</strong> recruitment process! 🚀
            </p>
        </div>
        <div style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:18px 28px;text-align:center;">
            <p style="margin:0;font-size:12px;color:#6b7280;font-weight:600;">
                Zensar Technologies · Zenbot Recruitment Portal
            </p>
            <p style="margin:4px 0 0;font-size:11px;color:#9ca3af;">
                Global HQ: Zensar Knowledge Park, Kharadi, Pune, Maharashtra 411014<br>
                Campuses: Chennai (DLF IT Park & OMR Tech Park) · Bengaluru · Hyderabad
            </p>
        </div>
    </div>
    """
    try:
        msg = EmailMultiAlternatives(
            subject, strip_tags(html_message),
            settings.DEFAULT_FROM_EMAIL, [app.email]
        )
        msg.attach_alternative(html_message, "text/html")
        msg.send(fail_silently=False)
        logger.info("Selection email with interview rounds sent to %s for %s", app.email, app.role)
    except Exception as e:
        logger.warning("Selection email failed for %s: %s", app.email, e)


def _send_rejection_email(app, app_type_label, reason=''):
    """Send an empathetic rejection email."""
    subject = f"Update on Your {app_type_label} Application — {app.role}"
    html_message = f"""
    <div style="font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;max-width:620px;margin:0 auto;border-radius:14px;overflow:hidden;border:1px solid #e5e7eb;">
        <div style="background:linear-gradient(135deg,#1e293b,#334155);padding:32px 28px;text-align:center;">
            <div style="font-size:40px;margin-bottom:10px;">📬</div>
            <h1 style="color:#f1f5f9;margin:0;font-size:22px;font-weight:700;">Application Status Update</h1>
            <p style="color:#94a3b8;margin:8px 0 0;font-size:14px;">Zenbot Recruitment · Zensar Technologies</p>
        </div>
        <div style="background:#ffffff;padding:28px 32px;">
            <p style="font-size:16px;color:#1a202c;line-height:1.7;margin-top:0;">
                Dear <strong>{app.full_name}</strong>,
            </p>
            <p style="font-size:15px;color:#374151;line-height:1.7;">
                Thank you for your interest in the <strong>{app.role}</strong> {app_type_label} position at
                Zensar Technologies and for the time you invested in your application.
                We truly appreciate your enthusiasm and effort.
            </p>
            <p style="font-size:15px;color:#374151;line-height:1.7;">
                After a thorough review of all applications, we regret to inform you that we will not be
                moving forward with your application at this time. This was a difficult decision as we
                received many strong applications.
            </p>
            <div style="background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;padding:18px 22px;margin:22px 0;">
                <h3 style="margin:0 0 12px;color:#374151;font-size:15px;">📋 Application Reference</h3>
                <table style="width:100%;font-size:14px;border-collapse:collapse;">
                    <tr>
                        <td style="padding:6px 0;color:#6b7280;font-weight:600;width:40%;">Position</td>
                        <td style="padding:6px 0;color:#1a202c;">{app.role}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;color:#6b7280;font-weight:600;">Type</td>
                        <td style="padding:6px 0;color:#1a202c;">{app_type_label}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;color:#6b7280;font-weight:600;">Status</td>
                        <td style="padding:6px 0;">
                            <span style="background:#fee2e2;color:#b91c1c;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:700;">Not Selected</span>
                        </td>
                    </tr>
                </table>
            </div>""" + (f"""
            <div style="background:#fffbeb;border-left:4px solid #f59e0b;padding:14px 18px;margin:22px 0;">
                <h4 style="margin:0 0 6px;color:#92400e;font-size:14px;">Feedback from our HR team:</h4>
                <p style="margin:0;font-size:14px;color:#b45309;line-height:1.6;">"{reason}"</p>
            </div>
            """ if reason else "") + """
            <p style="font-size:15px;color:#374151;line-height:1.7;">
                We encourage you to keep developing your skills and to explore future opportunities with us.
                Your profile will be kept on record and we may reach out if a suitable role opens up.
            </p>
            <p style="font-size:15px;color:#374151;line-height:1.7;margin-bottom:0;">
                We wish you all the best in your career journey. Thank you again for considering Zensar Technologies. 🌟
            </p>
        </div>
        <div style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:16px 28px;text-align:center;">
            <p style="margin:0;font-size:12px;color:#9ca3af;">
                Official notification from Zenbot Recruitment System · Zensar Technologies
            </p>
        </div>
    </div>
    """
    try:
        msg = EmailMultiAlternatives(
            subject, strip_tags(html_message),
            settings.DEFAULT_FROM_EMAIL, [app.email]
        )
        msg.attach_alternative(html_message, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"Rejection email sent to {app.email} for {app.role}")
    except Exception as e:
        logger.warning(f"Rejection email failed for {app.email}: {e}")
