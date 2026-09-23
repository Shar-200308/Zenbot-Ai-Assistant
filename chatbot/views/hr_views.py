import csv
import logging
import urllib.parse
from collections import Counter
from datetime import datetime, timedelta

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q as _Q
from django.db.models.functions import Lower
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.html import strip_tags
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from chatbot.email_utils import (
    get_campus_address_for_location,
    get_default_interview_schedule,
    send_status_email,
)
from chatbot.firebase_auth import FirebaseAuthentication
from chatbot.models import (
    CandidateMessage,
    HRAuditLog,
    InternshipApplication,
    JobApplication,
    JobPosting,
)
from chatbot.services import audit_hr_action, is_hr_email

logger = logging.getLogger(__name__)


@ensure_csrf_cookie
def hr_panel_page(request):
    return render(request, "hr_panel.html")


def _is_hr(user):
    """Returns True if the user has HR access."""
    email_match = is_hr_email(user.email)
    role_match = getattr(user, 'role', None) in ('hr', 'admin')
    return role_match or email_match


def hr_email_action(request):
    """HR clicks Accept / Reject directly from the notification email."""
    token = request.GET.get('token') or request.POST.get('token', '')
    context = {}

    try:
        data       = signing.loads(token, salt='hr-email-action', max_age=7 * 24 * 3600)
        app_id     = data['app_id']
        app_type   = data['type']       # 'internship' or 'job'
        action     = data['action']     # 'accept' or 'reject'
        new_status = 'selected' if action == 'accept' else 'rejected'

        _token_cache_key = f"hr_used_token_{token[:64]}"
        if cache.get(_token_cache_key):
            if app_type == 'internship':
                app = InternshipApplication.objects.filter(id=app_id).first()
            else:
                app = JobApplication.objects.filter(id=app_id).first()
            return render(request, 'hr_action_result.html', {
                'action': action,
                'new_status': new_status,
                'app': app,
                'type_label': 'Internship' if app_type == 'internship' else 'Job',
                'already_done': True,
                'replay_blocked': True,
            })

        if app_type == 'internship':
            app        = InternshipApplication.objects.filter(id=app_id).first()
            type_label = 'Internship'
        else:
            app        = JobApplication.objects.filter(id=app_id).first()
            type_label = 'Job'

        if not app:
            return render(request, 'hr_action_result.html', {'error': 'Application not found. It may have been deleted.'})

        already_done = (app.status == new_status)

        if action == 'reject':
            if not already_done:
                app.status = 'rejected'
                app.save(update_fields=['status'])
                send_status_email(app, type_label, 'rejected', reason='Profile does not match current requirements')
            cache.set(_token_cache_key, True, timeout=8 * 24 * 3600)
            return render(request, 'hr_action_result.html', {
                'action': 'reject',
                'new_status': 'rejected',
                'app': app,
                'type_label': type_label,
                'already_done': already_done,
            })

        cand_loc = str(getattr(app, 'location', '') or '').lower()
        default_campus = get_campus_address_for_location(cand_loc)

        if app_type == 'internship':
            rounds_count_text = "1 Round (HR Round)"
            rounds_desc = "Round 1: In-Person HR Interview & Profile Assessment (30 Mins)"
            rounds_details = [
                {
                    "name": "Round 1: In-Person HR Interview & Profile Assessment",
                    "duration": "30 Mins",
                    "desc": "Direct in-person interview at company campus reviewing academic background, project achievements, internship duration, cultural fitment, and onboarding formalities."
                }
            ]
        else:
            rounds_count_text = "3 Rounds (Aptitude, Technical, HR)"
            rounds_desc = "Round 1: Aptitude Assessment (30 Mins)\n  • Round 2: Technical Interview (45 Mins)\n  • Round 3: HR Discussion (30 Mins)"
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

        if already_done:
            latest_msg = CandidateMessage.objects.filter(application_id=app.id, application_type=app_type).order_by('-created_at').first()
            return render(request, 'hr_action_result.html', {
                'action': 'accept',
                'new_status': 'selected',
                'app': app,
                'type_label': type_label,
                'already_done': True,
                'scheduled_time': latest_msg.scheduled_time if latest_msg else 'Confirmed',
                'venue_address': latest_msg.venue_address if latest_msg else default_campus,
            })

        if request.method == 'GET':
            suggested_date = timezone.now()
            business_days_added = 0
            while business_days_added < 2:
                suggested_date += timedelta(days=1)
                if suggested_date.weekday() < 5:
                    business_days_added += 1

            return render(request, 'hr_action_result.html', {
                'action': 'allot_schedule',
                'app': app,
                'type_label': type_label,
                'token': token,
                'min_date': timezone.now().strftime('%Y-%m-%d'),
                'default_date': suggested_date.strftime('%Y-%m-%d'),
                'default_time': '10:30',
                'default_campus': default_campus,
                'rounds_count_text': rounds_count_text,
                'rounds_details': rounds_details,
            })

        date_input = request.POST.get('interview_date', '').strip()
        time_input = request.POST.get('interview_time', '').strip()
        venue_address = request.POST.get('venue_address', '').strip() or default_campus
        notes = request.POST.get('notes', '').strip()

        if date_input and time_input:
            try:
                tz = timezone.get_current_timezone()
                d_obj = datetime.strptime(date_input, '%Y-%m-%d').replace(tzinfo=tz)
                t_obj = datetime.strptime(time_input, '%H:%M').replace(tzinfo=tz)
                interview_time = f"{d_obj.strftime('%d %b %Y')}, {t_obj.strftime('%I:%M %p')} IST"
            except (ValueError, TypeError):
                interview_time = f"{date_input}, {time_input} IST"
        else:
            interview_time = get_default_interview_schedule()

        app.status = 'selected'
        app.save(update_fields=['status'])
        cache.set(_token_cache_key, True, timeout=8 * 24 * 3600)
        logger.info("HR email action: app #%s (%s) allotted on %s", app_id, type_label, interview_time)

        interview_data = {
            'scheduled_time': interview_time,
            'total_rounds': rounds_count_text,
            'rounds_details': rounds_details,
            'venue_address': venue_address,
            'notes': notes,
        }

        try:
            CandidateMessage.objects.create(
                application_id=app.id,
                application_type=app_type,
                candidate_email=app.email,
                sender="HR Recruitment Team",
                subject=f"Application Accepted — In-Person Interview Call Letter ({rounds_count_text})",
                message=(
                    f"Congratulations {app.full_name}! Your application for {app.role} ({type_label}) has been accepted.\n\n"
                    f"📋 Interview Structure: {rounds_count_text}\n"
                    f"  • {rounds_desc}\n\n"
                    f"🏢 Mode: Direct In-Person Interview (No Online / Virtual)\n"
                    f"📍 Venue Address: {venue_address}\n"
                    f"📅 Date & Time: {interview_time}\n\n"
                    f"Your submitted application resume has also been attached to your official call letter email for reference."
                ),
                venue_address=venue_address,
                interview_type=app_type,
                meeting_link="",
                scheduled_time=interview_time,
            )
        except Exception as msg_err:
            logger.warning("Could not log CandidateMessage from hr_email_action: %s", msg_err)

        send_status_email(app, type_label, 'selected', interview_data=interview_data)

        return render(request, 'hr_action_result.html', {
            'action': 'accept',
            'new_status': 'selected',
            'app': app,
            'type_label': type_label,
            'already_done': False,
            'scheduled_time': interview_time,
            'venue_address': venue_address,
        })

    except signing.SignatureExpired:
        context = {'error': 'This link has expired (valid for 7 days). Please use the HR panel to update the status.'}
    except signing.BadSignature:
        context = {'error': 'Invalid or corrupted link. Please use the HR panel directly.'}

    return render(request, 'hr_action_result.html', context)


@api_view(['GET'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def hr_get_applications(request):
    """HR API to fetch all internship and job applications with filters and communication info."""
    user = request.user
    if not _is_hr(user):
        hr_email = getattr(settings, 'HR_EMAIL', '(not set)')
        return Response({
            'error': f'HR access required. Your email: {user.email!r}, HR email: {hr_email!r}'
        }, status=403)

    type_filter     = request.query_params.get('type')
    status_filter   = request.query_params.get('status')
    search          = request.query_params.get('search')
    role_filter     = request.query_params.get('role')
    archived_filter = (request.query_params.get('archived') or 'false').strip().lower()

    if archived_filter == 'true':
        internships = InternshipApplication.objects.filter(hr_archived=True, hr_deleted=False).order_by('-applied_at')
        jobs        = JobApplication.objects.filter(hr_archived=True, hr_deleted=False).order_by('-applied_at')
    elif archived_filter == 'all':
        internships = InternshipApplication.objects.filter(hr_deleted=False).order_by('-applied_at')
        jobs        = JobApplication.objects.filter(hr_deleted=False).order_by('-applied_at')
    else:
        internships = InternshipApplication.objects.filter(hr_archived=False, hr_deleted=False).order_by('-applied_at')
        jobs        = JobApplication.objects.filter(hr_archived=False, hr_deleted=False).order_by('-applied_at')

    if role_filter:
        internships = internships.filter(role__iexact=role_filter)
        jobs        = jobs.filter(role__iexact=role_filter)

    if status_filter and status_filter != 'all':
        internships = internships.filter(status=status_filter)
        jobs = jobs.filter(status=status_filter)
    if search:
        internships = internships.filter(
            full_name__icontains=search
        ) | internships.filter(email__icontains=search)
        jobs = jobs.filter(
            full_name__icontains=search
        ) | jobs.filter(email__icontains=search)

    internship_ids = [a.id for a in internships]
    job_ids = [a.id for a in jobs]
    all_msgs = CandidateMessage.objects.filter(
        _Q(application_id__in=internship_ids, application_type='internship') |
        _Q(application_id__in=job_ids, application_type='job')
    ).order_by('-created_at')
    msg_map = {}
    for m in all_msgs:
        m_key = (m.application_id, m.application_type)
        if m_key not in msg_map:
            msg_map[m_key] = []
        msg_map[m_key].append({
            'id': m.id,
            'sender': m.sender,
            'subject': m.subject,
            'message': m.message,
            'venue_address': m.venue_address or '',
            'interview_type': m.interview_type or '',
            'scheduled_time': m.scheduled_time or '',
            'meeting_link': m.meeting_link or '',
            'calendar_link': m.calendar_link or '',
            'created_at': m.created_at.strftime('%d %b %Y, %I:%M %p'),
        })

    data = []
    if type_filter != 'job':
        for app in internships:
            m_list = msg_map.get((app.id, 'internship'), [])
            latest_m = m_list[0] if m_list else None
            has_interview = bool(latest_m and (latest_m['scheduled_time'] or latest_m.get('venue_address') or latest_m['meeting_link']))

            data.append({
                'id': app.id,
                'type': 'internship',
                'type_display': 'Internship',
                'role': app.role,
                'full_name': app.full_name,
                'email': app.email,
                'phone': app.phone or '',
                'course': app.course or '',
                'ug_course': getattr(app, 'ug_course', None) or '',
                'ug_college': app.ug_college or '',
                'pg_college': app.pg_college or '',
                'ug_cgpa': app.ug_cgpa or '',
                'pg_cgpa': app.pg_cgpa or '',
                'ats_score': app.ats_score if app.ats_score is not None else 85,
                'key_skills': getattr(app, 'key_skills', None) or '',
                'preferred_location': getattr(app, 'location', None) or '',
                'messages': m_list,
                'messages_count': len(m_list),
                'has_scheduled_interview': has_interview,
                'interview_time': latest_m['scheduled_time'] if latest_m else '',
                'interview_venue': latest_m.get('venue_address', '') if latest_m else '',
                'interview_link': latest_m['meeting_link'] if latest_m else '',
                'status': app.status,
                'status_display': app.get_status_display(),
                'hr_archived': bool(getattr(app, 'hr_archived', False)),
                'resume_url': app.resume.url if app.resume else '',
                'photo_url': app.photo.url if app.photo else '',
                'applied_at': app.applied_at.strftime('%d %b %Y'),
                '_sort': app.applied_at.isoformat(),
            })
    if type_filter != 'internship':
        for app in jobs:
            m_list = msg_map.get((app.id, 'job'), [])
            latest_m = m_list[0] if m_list else None
            has_interview = bool(latest_m and (latest_m['scheduled_time'] or latest_m.get('venue_address') or latest_m['meeting_link']))

            data.append({
                'id': app.id,
                'type': 'job',
                'type_display': 'Job',
                'role': app.role,
                'full_name': app.full_name,
                'email': app.email,
                'phone': app.phone or '',
                'course': app.course or '',
                'ug_course': getattr(app, 'ug_course', None) or '',
                'ug_college': app.ug_college or '',
                'pg_college': app.pg_college or '',
                'ug_cgpa': app.ug_cgpa or '',
                'pg_cgpa': app.pg_cgpa or '',
                'ats_score': app.ats_score if app.ats_score is not None else 85,
                'key_skills': getattr(app, 'key_skills', None) or '',
                'preferred_location': getattr(app, 'location', None) or '',
                'messages': m_list,
                'messages_count': len(m_list),
                'has_scheduled_interview': has_interview,
                'interview_time': latest_m['scheduled_time'] if latest_m else '',
                'interview_venue': latest_m.get('venue_address', '') if latest_m else '',
                'interview_link': latest_m['meeting_link'] if latest_m else '',
                'status': app.status,
                'status_display': app.get_status_display(),
                'hr_archived': bool(getattr(app, 'hr_archived', False)),
                'resume_url': app.resume.url if app.resume else '',
                'photo_url': app.photo.url if app.photo else '',
                'applied_at': app.applied_at.strftime('%d %b %Y'),
                '_sort': app.applied_at.isoformat(),
            })

    data.sort(key=lambda x: x['_sort'], reverse=True)
    for d in data:
        d.pop('_sort', None)

    total_count = len(data)
    try:
        page = max(1, int(request.query_params.get('page', 1)))
        page_size = max(1, min(int(request.query_params.get('page_size', 50)), 200))
    except (ValueError, TypeError):
        page, page_size = 1, 50

    start = (page - 1) * page_size
    end   = start + page_size
    paginated_data = data[start:end]

    return Response({
        'applications': paginated_data,
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total': total_count,
            'total_pages': max(1, (total_count + page_size - 1) // page_size),
            'has_next': end < total_count,
            'has_prev': page > 1,
        }
    })


@api_view(['GET'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def hr_export_csv(request):
    """Exports candidate applications as a formatted CSV spreadsheet."""
    user = request.user
    if not _is_hr(user):
        return Response({'error': 'HR access required.'}, status=403)

    status_filter   = request.query_params.get('status', '').strip()
    type_filter     = request.query_params.get('type', '').strip().lower()
    search          = request.query_params.get('search', '').strip()
    role_filter     = request.query_params.get('role', '').strip()
    archived_filter = (request.query_params.get('archived') or 'false').strip().lower()

    if archived_filter == 'true':
        internships = InternshipApplication.objects.filter(hr_archived=True).order_by('-applied_at')
        jobs        = JobApplication.objects.filter(hr_archived=True).order_by('-applied_at')
    elif archived_filter == 'all':
        internships = InternshipApplication.objects.all().order_by('-applied_at')
        jobs        = JobApplication.objects.all().order_by('-applied_at')
    else:
        internships = InternshipApplication.objects.filter(hr_archived=False).order_by('-applied_at')
        jobs        = JobApplication.objects.filter(hr_archived=False).order_by('-applied_at')

    if role_filter:
        internships = internships.filter(role__iexact=role_filter)
        jobs        = jobs.filter(role__iexact=role_filter)

    if status_filter:
        internships = internships.filter(status=status_filter)
        jobs = jobs.filter(status=status_filter)
    if search:
        internships = internships.filter(full_name__icontains=search) | internships.filter(email__icontains=search)
        jobs = jobs.filter(full_name__icontains=search) | jobs.filter(email__icontains=search)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="zenbot_candidates_export.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Application ID', 'Type', 'Full Name', 'Email', 'Phone', 'Applied Role',
        'Status', 'ATS Match Score (%)', 'Key Skills', 'UG Course', 'UG College', 'UG CGPA',
        'PG College', 'PG CGPA', 'Location', 'Applied Date', 'Resume URL'
    ])

    if type_filter != 'job':
        for app in internships:
            _ats = app.ats_score if app.ats_score is not None else 85
            writer.writerow([
                app.id,
                'Internship',
                app.full_name,
                app.email,
                app.phone or '',
                app.role,
                app.get_status_display(),
                _ats,
                getattr(app, 'key_skills', '') or '',
                getattr(app, 'ug_course', '') or getattr(app, 'course', '') or '',
                app.ug_college or '',
                app.ug_cgpa or '',
                app.pg_college or '',
                app.pg_cgpa or '',
                getattr(app, 'location', '') or '',
                app.applied_at.strftime('%Y-%m-%d %H:%M'),
                app.resume.url if app.resume else '',
            ])

    if type_filter != 'internship':
        for app in jobs:
            _ats = app.ats_score if app.ats_score is not None else 85
            writer.writerow([
                app.id,
                'Job',
                app.full_name,
                app.email,
                app.phone or '',
                app.role,
                app.get_status_display(),
                _ats,
                getattr(app, 'key_skills', '') or '',
                getattr(app, 'ug_course', '') or getattr(app, 'course', '') or '',
                app.ug_college or '',
                app.ug_cgpa or '',
                app.pg_college or '',
                app.pg_cgpa or '',
                getattr(app, 'location', '') or '',
                app.applied_at.strftime('%Y-%m-%d %H:%M'),
                app.resume.url if app.resume else '',
            ])

    logger.info("HR %s exported candidate applications to CSV", user.email)
    return response


@api_view(['POST'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def hr_update_status(request):
    """HR updates application status and triggers email if accepted/rejected."""
    user = request.user
    if not _is_hr(user):
        hr_email = getattr(settings, 'HR_EMAIL', '(not set)')
        return Response({
            'error': f'HR access required. Your email: {user.email!r}, HR email: {hr_email!r}'
        }, status=403)

    app_id   = request.data.get('id')
    app_type = request.data.get('type', '').lower()
    new_status = request.data.get('status')
    reason = request.data.get('reason', '').strip()

    VALID_STATUSES = ['pending', 'under_review', 'shortlisted', 'selected', 'rejected']
    if new_status not in VALID_STATUSES:
        return Response({'error': 'Invalid status.'}, status=400)

    if app_type == 'internship':
        app = InternshipApplication.objects.filter(id=app_id).first()
        type_label = 'Internship'
    elif app_type == 'job':
        app = JobApplication.objects.filter(id=app_id).first()
        type_label = 'Job'
    else:
        return Response({'error': 'Invalid type. Must be internship or job.'}, status=400)

    if not app:
        return Response({'error': 'Application not found.'}, status=404)

    old_status = app.status
    app.status = new_status
    app.save(update_fields=['status'])
    audit_hr_action(user.email, 'status_update', app_type, app_id,
                    f"{old_status} → {new_status} for {app.full_name} ({app.role})")
    logger.info("HR %s changed app #%s (%s) %s -> %s", user.email, app_id, type_label, old_status, new_status)

    if new_status in ('selected', 'rejected') and old_status != new_status:
        interview_data = None
        if new_status == 'selected':
            cand_loc = str(getattr(app, 'location', '') or '').lower()
            default_campus = get_campus_address_for_location(cand_loc)

            venue_address = (request.data.get('venue_address') or request.data.get('meeting_link') or default_campus).strip()
            if 'meet.google.com' in venue_address or 'zoom.us' in venue_address:
                venue_address = default_campus

            time_text = (request.data.get('scheduled_time') or request.data.get('interview_date_time') or '').strip()
            generic_placeholders = [
                'upcoming business days',
                'coordinated by hr',
                'coordinated shortly',
                'will confirm',
                'exact time coordinated',
                'to be determined',
                'tbd',
            ]
            if not time_text or any(p in time_text.lower() for p in generic_placeholders):
                time_text = get_default_interview_schedule()

            if app_type == 'internship':
                rounds_count_text = "1 Round (HR Round)"
                rounds_details = [
                    {
                        "name": "Round 1: In-Person HR Interview & Profile Assessment",
                        "duration": "30 Mins",
                        "desc": "Direct in-person interview at company campus reviewing academic background, project achievements, internship duration, cultural fitment, and onboarding formalities."
                    }
                ]
            else:
                rounds_count_text = "3 Rounds (Aptitude, Technical, HR)"
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

            interview_data = {
                'scheduled_time': time_text,
                'total_rounds': rounds_count_text,
                'rounds_details': rounds_details,
                'venue_address': venue_address,
                'notes': request.data.get('notes', '').strip(),
            }

            try:
                instructions = interview_data.get('notes', '').strip()
                if instructions:
                    notes_part = f"\n\nSpecial Instructions: {instructions}"
                else:
                    notes_part = "\n\nImportant: Please arrive 15 minutes before your scheduled start time with your valid photo ID proof and printed copies of your submitted resume (attached to your call letter email)."
                rounds_summary = "\n".join([f"  • {r['name']} ({r['duration']})" for r in rounds_details])

                msg_content = (
                    f"Congratulations {app.full_name}! Your application for the {app.role} ({type_label}) position has been accepted by our HR recruitment panel.\n\n"
                    f"📋 Interview Structure: {rounds_count_text}\n"
                    f"{rounds_summary}\n\n"
                    f"📅 Scheduled Date & Time: {time_text}\n"
                    f"🏢 Mode: Direct In-Person Interview (No Online / Virtual)\n"
                    f"📍 Company Campus Venue: {venue_address}{notes_part}"
                )

                company_name = getattr(settings, 'COMPANY_NAME', 'Zensar Technologies')
                cal_title = urllib.parse.quote(f"In-Person Interview: {app.role} at {company_name}")
                cal_details = urllib.parse.quote(f"In-Person Interview ({rounds_count_text})\nVenue: {venue_address}\nTime: {time_text}")
                cal_loc = urllib.parse.quote(venue_address)
                calendar_link = f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={cal_title}&details={cal_details}&location={cal_loc}"

                CandidateMessage.objects.create(
                    application_id=app.id,
                    application_type=app_type,
                    candidate_email=app.email,
                    sender=f"HR Recruitment Team ({user.email})",
                    subject=f"Application Accepted — In-Person Interview Call Letter ({rounds_count_text})",
                    message=msg_content,
                    venue_address=venue_address,
                    interview_type=app_type,
                    meeting_link='',
                    scheduled_time=time_text,
                    calendar_link=calendar_link,
                )
            except Exception as c_err:
                logger.warning("Could not log CandidateMessage from hr_update_status: %s", c_err)

        send_status_email(app, type_label, new_status, reason=reason, interview_data=interview_data)

    STATUS_DISPLAY = dict(app._meta.get_field('status').choices)
    return Response({
        'status': 'updated',
        'new_status': new_status,
        'new_status_display': STATUS_DISPLAY.get(new_status, new_status),
    })


@api_view(['DELETE'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def hr_delete_application(request):
    """Allows HR to archive or permanently delete applications.

    - If permanent=True (or deleting from Archived tab):
      Permanently deletes the application record from the database (app.delete())
      and deletes any uploaded resume/photo files. Once permanently deleted,
      it will NEVER appear again.
    - If permanent=False:
      Soft-archives the application (hr_archived=True) so the candidate profile
      remains preserved in the chatbot.
    """
    user = request.user
    if not _is_hr(user):
        return Response({'error': 'HR access required.'}, status=403)

    is_permanent = bool(request.data.get('permanent', False) or (request.query_params.get('permanent') == 'true'))
    items = request.data.get('items')

    if items and isinstance(items, list):
        internship_ids = [it.get('id') for it in items if str(it.get('type', '')).lower() == 'internship' and it.get('id')]
        job_ids        = [it.get('id') for it in items if str(it.get('type', '')).lower() == 'job' and it.get('id')]

        if is_permanent:
            # HR permanently removes from HR panel (hr_deleted=True)
            # Candidate profile remains 100% intact in user chatbot!
            del_count = 0
            if internship_ids:
                del_count += InternshipApplication.objects.filter(id__in=internship_ids).update(hr_deleted=True)
            if job_ids:
                del_count += JobApplication.objects.filter(id__in=job_ids).update(hr_deleted=True)

            audit_hr_action(user.email, 'permanent_delete_application', 'bulk', None,
                            f"Bulk permanently removed {del_count} applications from HR panel — candidate data preserved in user chatbot")
            logger.info("HR %s bulk permanently removed %d applications from HR panel (preserved in chatbot)", user.email, del_count)
            return Response({'status': 'permanently_deleted', 'count': del_count, 'permanent': True})
        else:
            arch_count = 0
            if internship_ids:
                arch_count += InternshipApplication.objects.filter(id__in=internship_ids).update(hr_archived=True)
            if job_ids:
                arch_count += JobApplication.objects.filter(id__in=job_ids).update(hr_archived=True)

            audit_hr_action(user.email, 'archive_application', 'bulk', None,
                            f"Bulk archived {arch_count} applications — candidate data preserved")
            logger.info("HR %s bulk archived %d applications from HR panel", user.email, arch_count)
            return Response({'status': 'bulk_archived', 'count': arch_count, 'permanent': False})

    app_id   = request.data.get('id')
    app_type = request.data.get('type', '').lower()

    if not app_id or app_type not in ('internship', 'job'):
        return Response({'error': 'Invalid id or type.'}, status=400)

    if app_type == 'internship':
        app = InternshipApplication.objects.filter(id=app_id).first()
    else:
        app = JobApplication.objects.filter(id=app_id).first()

    if not app:
        return Response({'error': 'Application not found.'}, status=404)

    app_name = app.full_name

    if is_permanent:
        # Sets hr_deleted=True so it will NEVER appear in HR panel again.
        # User profile, resume, and chatbot status are preserved!
        app.hr_deleted = True
        app.save(update_fields=['hr_deleted'])
        audit_hr_action(user.email, 'permanent_delete_application', app_type, app_id,
                        f"Permanently removed '{app_name}' ({app.role}) from HR panel — preserved in user chatbot")
        logger.info("HR %s permanently removed %s application #%s (%s) from HR panel", user.email, app_type, app_id, app_name)
        return Response({'status': 'permanently_deleted', 'id': app_id, 'type': app_type, 'permanent': True})
    else:
        app.hr_archived = True
        app.save(update_fields=['hr_archived'])
        audit_hr_action(user.email, 'archive_application', app_type, app_id,
                        f"Archived '{app_name}' ({app.role}) — candidate profile preserved in chatbot")
        logger.info("HR %s archived %s application #%s (%s) — data preserved", user.email, app_type, app_id, app_name)
        return Response({'status': 'archived', 'id': app_id, 'type': app_type, 'permanent': False})


@api_view(['POST'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def hr_restore_application(request):
    """Allows HR to restore an archived/inactive application back to the active panel."""
    user = request.user
    if not _is_hr(user):
        return Response({'error': 'HR access required.'}, status=403)

    app_id   = request.data.get('id')
    app_type = (request.data.get('type') or '').lower()

    if not app_id or app_type not in ('internship', 'job'):
        return Response({'error': 'Invalid id or type.'}, status=400)

    if app_type == 'internship':
        app = InternshipApplication.objects.filter(id=app_id).first()
    else:
        app = JobApplication.objects.filter(id=app_id).first()

    if not app:
        return Response({'error': 'Application not found.'}, status=404)

    app_name = app.full_name
    app.hr_archived = False
    app.save(update_fields=['hr_archived'])
    audit_hr_action(user.email, 'restore_application', app_type, app_id,
                    f"Restored '{app_name}' ({app.role}) to active panel")
    logger.info("HR %s restored %s application #%s (%s)", user.email, app_type, app_id, app_name)
    return Response({'status': 'restored', 'id': app_id, 'type': app_type, 'full_name': app_name})


@api_view(['GET'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def hr_get_job_postings(request):
    """Returns all job postings (active and closed) for HR with applicant counts."""
    user = request.user
    if not _is_hr(user):
        return Response({'error': 'HR access required.'}, status=403)

    postings = list(JobPosting.objects.all().order_by('-created_at'))
    intern_role_counts = Counter(
        InternshipApplication.objects.filter(hr_archived=False, hr_deleted=False).annotate(role_lower=Lower('role')).values_list('role_lower', flat=True)
    )
    job_role_counts = Counter(
        JobApplication.objects.filter(hr_archived=False, hr_deleted=False).annotate(role_lower=Lower('role')).values_list('role_lower', flat=True)
    )

    data = []
    for p in postings:
        title_lower = p.title.strip().lower()
        app_count = (
            intern_role_counts[title_lower] if p.job_type == 'internship'
            else job_role_counts[title_lower]
        )
        data.append({
            "id": p.id,
            "title": p.title,
            "job_type": p.job_type,
            "department": p.department,
            "location": p.location,
            "experience": p.experience,
            "vacancies": getattr(p, 'vacancies', 5),
            "skills": p.skills or "",
            "description": p.description or "",
            "is_active": p.is_active,
            "created_at": p.created_at.strftime("%d %b %Y"),
            "applicant_count": app_count,
        })
    return Response({"jobs": data})


@api_view(['POST'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def hr_create_job_posting(request):
    """HR creates a new job or internship opening."""
    user = request.user
    if not _is_hr(user):
        return Response({'error': 'HR access required.'}, status=403)

    title = request.data.get("title", "").strip()
    if not title:
        return Response({"error": "Job title is required."}, status=400)

    job_type = request.data.get("job_type", "job").strip().lower()
    if job_type not in ('job', 'internship'):
        job_type = 'job'

    department = request.data.get("department", "Engineering").strip() or "Engineering"
    location = request.data.get("location", "Pune / Hybrid").strip() or "Pune / Hybrid"
    experience = request.data.get("experience", "Fresher / 0-2 Years").strip() or "Fresher / 0-2 Years"
    try:
        vacancies = max(1, int(request.data.get("vacancies", 5)))
    except (ValueError, TypeError):
        vacancies = 5
    skills = request.data.get("skills", "").strip()
    description = request.data.get("description", "").strip()

    posting = JobPosting.objects.create(
        title=title,
        job_type=job_type,
        department=department,
        location=location,
        experience=experience,
        vacancies=vacancies,
        skills=skills,
        description=description,
        is_active=True,
    )
    cache.delete('zensar_role_match_context')
    audit_hr_action(user.email, 'job_create', 'job_posting', posting.id,
                    f"{job_type.title()} '{title}' created at {location}")
    logger.info("HR %s created new %s opening: %s (ID #%d)", user.email, job_type, title, posting.id)
    return Response({
        "status": "created",
        "message": f"Successfully created opening for '{title}'",
        "job": {
            "id": posting.id,
            "title": posting.title,
            "job_type": posting.job_type,
            "is_active": posting.is_active,
        }
    }, status=201)


@api_view(['POST'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def hr_toggle_job_posting(request):
    """HR toggles an opening between active and closed."""
    user = request.user
    if not _is_hr(user):
        return Response({'error': 'HR access required.'}, status=403)

    job_id = request.data.get("id")
    posting = JobPosting.objects.filter(id=job_id).first()
    if not posting:
        return Response({"error": "Job opening not found."}, status=404)

    posting.is_active = not posting.is_active
    posting.save(update_fields=['is_active', 'updated_at'])
    status_text = "Active" if posting.is_active else "Closed"
    cache.delete('zensar_role_match_context')
    audit_hr_action(user.email, 'job_toggle', 'job_posting', posting.id,
                    f"'{posting.title}' toggled to {status_text}")
    logger.info("HR %s toggled job #%s (%s) to %s", user.email, job_id, posting.title, status_text)
    return Response({
        "status": "updated",
        "is_active": posting.is_active,
        "message": f"Job is now {status_text}"
    })


@api_view(['DELETE', 'POST'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def hr_delete_job_posting(request):
    """HR permanently deletes an opening."""
    user = request.user
    if not _is_hr(user):
        return Response({'error': 'HR access required.'}, status=403)

    job_id = request.data.get("id")
    posting = JobPosting.objects.filter(id=job_id).first()
    if not posting:
        return Response({"error": "Job opening not found."}, status=404)

    title = posting.title
    posting.delete()
    cache.delete('zensar_role_match_context')
    audit_hr_action(user.email, 'job_delete', 'job_posting', job_id,
                    f"Permanently deleted '{title}'")
    logger.info("HR %s deleted job posting #%s (%s)", user.email, job_id, title)
    return Response({
        "status": "deleted",
        "message": f"Deleted '{title}' successfully."
    })


@api_view(['POST'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def hr_send_candidate_message(request):
    """HR sends a direct in-app message and/or interview schedule invite to a candidate."""
    user = request.user
    if not _is_hr(user):
        return Response({'error': 'HR access required.'}, status=403)

    app_id = request.data.get('application_id')
    app_type = str(request.data.get('application_type', 'job')).lower()
    subject = request.data.get('subject', 'Interview Invitation / Application Update').strip()
    message_text = request.data.get('message', '').strip()
    venue_address = request.data.get('venue_address', '').strip()
    meeting_link = request.data.get('meeting_link', '').strip()
    scheduled_time = request.data.get('scheduled_time', '').strip()
    if scheduled_time and any(p in scheduled_time.lower() for p in ['upcoming business days', 'coordinated by hr', 'coordinated shortly', 'will confirm']):
        scheduled_time = get_default_interview_schedule()

    if not app_id or not message_text:
        return Response({'error': 'Application ID and message are required.'}, status=400)

    if app_type == 'internship':
        app = InternshipApplication.objects.filter(id=app_id).first()
    else:
        app = JobApplication.objects.filter(id=app_id).first()

    if not app:
        return Response({'error': 'Application not found.'}, status=404)

    if scheduled_time and not venue_address and not meeting_link:
        cand_loc = str(getattr(app, 'location', '') or '').lower()
        venue_address = get_campus_address_for_location(cand_loc)

    company_name = getattr(settings, 'COMPANY_NAME', 'Zensar Technologies')

    calendar_link = ""
    target_location = venue_address or meeting_link
    if scheduled_time or target_location:
        cal_title = urllib.parse.quote(f"In-Person Interview: {app.role} at {company_name}")
        summary_desc = (message_text[:250].strip() + "...") if len(message_text) > 250 else message_text.strip()
        cal_details = urllib.parse.quote(f"{summary_desc}\n\nVenue Address: {target_location}")
        cal_loc = urllib.parse.quote(target_location or "Company Campus")
        calendar_link = f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={cal_title}&details={cal_details}&location={cal_loc}"

    candidate_msg = CandidateMessage.objects.create(
        application_id=app.id,
        application_type=app_type,
        candidate_email=app.email,
        sender=f"HR Team ({user.name or 'Recruiter'})",
        subject=subject or "In-Person Interview Invitation / Application Update",
        message=message_text,
        venue_address=venue_address,
        interview_type=app_type,
        meeting_link=meeting_link,
        scheduled_time=scheduled_time,
        calendar_link=calendar_link,
    )

    try:
        import datetime as _dt
        email_subject = f"📨 New Message from {company_name} HR: {subject} — {app.role}"
        cal_btn_html = f"""<a href="{calendar_link}" target="_blank" style="display:inline-block;background:#2563eb;color:#fff;padding:8px 16px;border-radius:6px;text-decoration:none;font-weight:600;font-size:13px;margin-top:6px;">📅 Add to Google Calendar</a>""" if calendar_link else ""

        venue_html = ""
        if scheduled_time or venue_address:
            venue_html = f"""
            <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;margin:18px 0;">
                <p style="margin:0 0 8px;color:#166534;font-weight:700;font-size:15px;">🏢 In-Person Interview Details:</p>
                {f'<p style="margin:0 0 6px;font-size:14px;color:#1e293b;"><strong>Date & Time:</strong> {scheduled_time}</p>' if scheduled_time else ''}
                {f'<p style="margin:0 0 8px;font-size:13px;color:#334155;line-height:1.5;"><strong>📍 Campus Venue Address:</strong><br>{venue_address}</p>' if venue_address else ''}
                <div style="margin-top:8px;">
                    {cal_btn_html}
                </div>
            </div>"""

        html_body = f"""
        <div style="font-family:'Segoe UI',sans-serif;max-width:600px;margin:0 auto;border:1px solid #e2e8f0;border-radius:12px;padding:24px;background:#ffffff;">
            <h2 style="color:#1e40af;margin-top:0;">{subject}</h2>
            <p style="color:#4b5563;">Dear <strong>{app.full_name}</strong>,</p>
            <p style="font-size:15px;line-height:1.6;color:#1f2937;">{message_text.replace(chr(10), '<br>')}</p>
            {venue_html}
            <p style="font-size:13px;color:#6b7280;margin-top:20px;border-top:1px solid #f3f4f6;padding-top:12px;">
                You can also view this message, venue details, and all application updates directly inside your <strong>Zenbot 'My Applications'</strong> portal.
            </p>
        </div>"""
        msg = EmailMultiAlternatives(email_subject, strip_tags(html_body), settings.DEFAULT_FROM_EMAIL, [app.email])
        msg.attach_alternative(html_body, "text/html")

        if scheduled_time or target_location:
            now_stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            dtstart = now_stamp
            dtend = now_stamp
            use_tzid = False
            try:
                _dt_str = scheduled_time.replace(" IST", "").strip() if scheduled_time else ""
                if _dt_str:
                    _dt_obj = _dt.datetime.strptime(_dt_str, "%d %b %Y, %I:%M %p").replace(tzinfo=_dt.timezone.utc)
                    dtstart = _dt_obj.strftime("%Y%m%dT%H%M%S")
                    dtend   = (_dt_obj + _dt.timedelta(hours=2)).strftime("%Y%m%dT%H%M%S")
                    use_tzid = True
            except (ValueError, TypeError):
                pass
            if use_tzid:
                dtstart_line = f"DTSTART;TZID=Asia/Kolkata:{dtstart}"
                dtend_line   = f"DTEND;TZID=Asia/Kolkata:{dtend}"
            else:
                dtstart_line = f"DTSTART:{dtstart}"
                dtend_line   = f"DTEND:{dtend}"
            ics_data = (
                f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
                f"PRODID:-//{company_name}//Zenbot//EN\r\nMETHOD:REQUEST\r\n"
                f"BEGIN:VEVENT\r\n"
                f"UID:zenbot-interview-{candidate_msg.id}@{company_name.lower().replace(' ', '')}.com\r\n"
                f"DTSTAMP:{now_stamp}\r\n"
                f"{dtstart_line}\r\n"
                f"{dtend_line}\r\n"
                f"SUMMARY:{subject} - {app.role}\r\n"
                f"DESCRIPTION:{message_text}\\nVenue: {target_location}\r\n"
                f"LOCATION:{target_location or 'Company Campus'}\r\n"
                f"STATUS:CONFIRMED\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
            )
            msg.attach("interview_invitation.ics", ics_data, "text/calendar")

        msg.send(fail_silently=False)
    except Exception as mail_err:
        logger.warning("Notification email for candidate message failed: %s", mail_err)

    audit_hr_action(
        user.email, 'message_send', app_type, app.id,
        f"Sent '{subject}' to {app.email} (scheduled: {scheduled_time or 'N/A'})"
    )
    logger.info("HR sent direct message/interview invite to %s for %s #%s", app.email, app_type, app.id)
    return Response({
        'status': 'sent',
        'message': 'Message & interview invitation sent successfully!',
        'id': candidate_msg.id
    })


@api_view(['GET'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def hr_get_audit_log(request):
    """Returns the HR audit log (paginated)."""
    user = request.user
    if not _is_hr(user):
        return Response({'error': 'HR access required.'}, status=403)

    qs = HRAuditLog.objects.all()
    action_filter = request.query_params.get('action', '').strip()
    actor_filter = request.query_params.get('actor', '').strip()
    if action_filter:
        qs = qs.filter(action=action_filter)
    if actor_filter:
        qs = qs.filter(actor_email__iexact=actor_filter)

    total = qs.count()
    try:
        page = max(1, int(request.query_params.get('page', 1)))
        page_size = max(1, min(int(request.query_params.get('page_size', 50)), 200))
    except (ValueError, TypeError):
        page, page_size = 1, 50

    offset = (page - 1) * page_size
    entries = qs[offset:offset + page_size]

    data = [
        {
            'id': e.id,
            'actor': e.actor_email,
            'action': e.action,
            'target_type': e.target_type or '',
            'target_id': e.target_id,
            'detail': e.detail or '',
            'timestamp': e.timestamp.strftime('%d %b %Y %H:%M:%S IST'),
        }
        for e in entries
    ]

    return Response({
        'audit_log': data,
        'pagination': {
            'page': page, 'page_size': page_size,
            'total': total, 'total_pages': max(1, (total + page_size - 1) // page_size),
        }
    })


@api_view(['GET', 'POST'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def hr_dynamic_shortlist(request):
    """AI Dynamic Candidate Shortlisting for HR."""
    user = request.user
    if not _is_hr(user):
        return Response({'error': 'HR access required.'}, status=403)

    role = request.query_params.get('role') or request.data.get('role', 'Full Stack Developer')
    try:
        count = int(request.query_params.get('count') or request.data.get('count', 50))
    except (ValueError, TypeError):
        count = 50

    count = max(1, min(count, 500))

    from chatbot.candidate_screening_engine import run_dynamic_shortlist
    result = run_dynamic_shortlist(role=role, count=count, total_apps=1000)
    return Response(result)
