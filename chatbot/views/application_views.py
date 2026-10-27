import concurrent.futures
import contextlib
import json
import logging
import re
from io import BytesIO
from urllib.parse import urlparse

from django.core import signing
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import FileResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request as DRFRequest
from rest_framework.response import Response

from chatbot.ai import ai_engine
from chatbot.firebase_auth import FirebaseAuthentication
from chatbot.models import (
    CandidateMessage,
    ChatMessage,
    InternshipApplication,
    JobApplication,
    JobPosting,
)
from chatbot.services import check_honeypot
from chatbot.tasks import _cache_key, precompute_resume_analysis

from .common import (
    _resolve_ats_score_and_skills,
    format_short_name,
)

logger = logging.getLogger(__name__)


def internship_apply_page(request):
    role = request.GET.get('role', '').strip()
    location = request.GET.get('location', '').strip()
    active_postings = list(JobPosting.objects.filter(is_active=True, job_type='internship').values('title', 'location', 'department', 'experience'))
    seen_titles = set()
    unique_postings = []
    for p in active_postings:
        if p['title'] not in seen_titles:
            seen_titles.add(p['title'])
            unique_postings.append(p)
    active_postings = unique_postings
    active_roles = [p['title'] for p in active_postings]
    if not active_roles:
        active_roles = ["AI / ML Developer Intern", "Software Engineering Intern", "Quality Engineering & Testing Intern", "Data Science Intern"]
        active_postings = [
            {'title': 'AI / ML Developer Intern', 'location': 'Chennai, Tamil Nadu (DLF IT Park)', 'department': 'Artificial Intelligence', 'experience': 'Fresher'},
            {'title': 'Software Engineering Intern', 'location': 'Pune, Maharashtra (Global HQ, Kharadi)', 'department': 'Engineering', 'experience': 'Fresher'},
            {'title': 'Quality Engineering & Testing Intern', 'location': 'Chennai, Tamil Nadu (DLF IT Park)', 'department': 'Testing & QA', 'experience': 'Fresher'},
        ]
    if not role:
        role = active_roles[0]
    active_roles = [role]
    return render(request, "internship_form.html", {
        "role": role,
        "location": location,
        "active_roles": active_roles,
        "active_postings": active_postings,
    })


def job_apply_page(request):
    role = request.GET.get('role', '').strip()
    location = request.GET.get('location', '').strip()
    active_postings = list(JobPosting.objects.filter(is_active=True, job_type='job').values('title', 'location', 'department', 'experience'))
    seen_titles = set()
    unique_postings = []
    for p in active_postings:
        if p['title'] not in seen_titles:
            seen_titles.add(p['title'])
            unique_postings.append(p)
    active_postings = unique_postings
    active_roles = [p['title'] for p in active_postings]
    if not active_roles:
        active_roles = ["Software Engineer", "Quality Engineer (Automation, Mobile & AI-Led Testing)", "Full Stack Python Developer", "QA Automation Engineer"]
        active_postings = [
            {'title': 'Software Engineer', 'location': 'Pune, Maharashtra (Global HQ, Kharadi)', 'department': 'Engineering', 'experience': '0-2 Years / Freshers Eligible'},
            {'title': 'Quality Engineer (Automation, Mobile & AI-Led Testing)', 'location': 'Pune, Maharashtra (Global HQ, Kharadi)', 'department': 'Testing & QA', 'experience': '0-3 Years'},
            {'title': 'Full Stack Python Developer', 'location': 'Chennai, Tamil Nadu (OMR Tech Park)', 'department': 'Engineering', 'experience': '0-2 Years'},
            {'title': 'QA Automation Engineer', 'location': 'Pune, Maharashtra (Global HQ, Kharadi)', 'department': 'Testing & QA', 'experience': '0-3 Years'},
        ]
    if not role:
        role = active_roles[0]
    active_roles = [role]
    return render(request, "job_form.html", {
        "role": role,
        "location": location,
        "active_roles": active_roles,
        "active_postings": active_postings,
    })


@api_view(['POST'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def upload_resume(request):
    try:
        resume_file = request.FILES.get("resume")
        if not resume_file:
            return Response({"error": "No file uploaded"}, status=400)

        if not resume_file.name.lower().endswith(".pdf"):
            return Response({"error": "Only PDF files are accepted"}, status=400)

        allowed_mime_types = ["application/pdf", "application/x-pdf"]
        if hasattr(resume_file, 'content_type') and resume_file.content_type not in allowed_mime_types:
            return Response({"error": "Invalid file type. Only PDF files are accepted."}, status=400)

        if resume_file.size > 5 * 1024 * 1024:
            return Response({"error": "File size must be under 5MB"}, status=400)

        import PyPDF2
        raw_pdf_content = resume_file.read()
        resume_file.seek(0)
        pdf_bytes = BytesIO(raw_pdf_content)

        resume_text = ""
        try:
            reader = PyPDF2.PdfReader(pdf_bytes)
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    resume_text += text + "\n"
        except Exception as e:
            logger.warning("PyPDF2 Extraction Warning: %s", e)
            resume_text = ""

        word_count = len(resume_text.strip().split())
        if word_count < 30:
            logger.info(
                "PyPDF2 extracted only %d words from '%s'. Triggering AI Vision OCR fallback for scanned resume...",
                word_count, resume_file.name
            )
            ocr_text = ai_engine.extract_text_with_ocr(raw_pdf_content)
            if ocr_text and len(ocr_text.strip().split()) >= 15:
                resume_text = ocr_text
                logger.info("AI Vision OCR successfully extracted %d characters.", len(resume_text))
            elif not resume_text.strip():
                return Response({
                    "error": "Could not extract text from this PDF. Please ensure the document is clear and readable."
                }, status=400)

        user = request.user
        user_name = format_short_name(user.name) if user.name else (
            format_short_name(user.email.split("@")[0]) if user.email else "User"
        )

        user.resume_text = resume_text
        user.save(update_fields=['resume_text'])

        try:
            pdf_bytes.seek(0)
            analyzed_path = f"analyzed_resumes/user_{user.id}.pdf"
            if default_storage.exists(analyzed_path):
                with contextlib.suppress(Exception):
                    default_storage.delete(analyzed_path)
            default_storage.save(analyzed_path, ContentFile(pdf_bytes.read()))
            logger.info("Persisted analyzed resume for user %s -> %s", user.email, analyzed_path)
        except Exception as se:
            logger.warning("Could not persist analyzed resume file: %s", se)

        return Response({
            "status": "ask_role_type",
            "user": user_name,
            "resume_name": resume_file.name
        })

    except Exception as e:
        exc_str = str(e)
        logger.error("Resume Upload Error: %s", e)
        is_rate_limit = "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str
        is_unavailable = "503" in exc_str or "UNAVAILABLE" in exc_str
        is_network_err = (
            "getaddrinfo" in exc_str or "ConnectionError" in exc_str or
            "ConnectionReset" in exc_str or "RemoteDisconnected" in exc_str or
            isinstance(e, (OSError, ConnectionError))
        )
        if is_network_err:
            return Response({"error": "Network error: AI service is currently unreachable. Please check your connection."}, status=503)
        if is_rate_limit or is_unavailable:
            return Response({"error": "AI service is temporarily busy. Please wait a moment and try again."}, status=503)
        return Response({"error": "Failed to process resume. Please try again."}, status=500)


@api_view(['POST'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def suggest_roles(request):
    try:
        user = request.user
        user_name = format_short_name(user.name) if user.name else (
            format_short_name(user.email.split("@")[0]) if user.email else "User"
        )
        requested_type = request.data.get("type", "job")
        if requested_type == "internship":
            requested_type = "intern"
        requested_location = request.data.get("location", None)

        resume_text = user.resume_text
        if not resume_text:
            return Response({"error": "No resume found. Please upload your resume first."}, status=400)

        role_suggestions_json = ai_engine.suggest_roles_from_resume(
            resume_text, user_name, requested_type, requested_location=requested_location
        )
        try:
            role_suggestions = json.loads(role_suggestions_json)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse role suggestions JSON: %s | Raw: %s", e, role_suggestions_json[:300])
            return Response({"error": "Could not analyze resume. Please try uploading again or use a different PDF."}, status=500)

        if not role_suggestions.get("is_resume", True):
            return Response({"error": role_suggestions.get("error", "This is not a resume, upload your resume.")}, status=400)

        role_items = [
            {
                "role": r.get('role', ''),
                "location": r.get('location', 'Chennai, Tamil Nadu (OMR Tech Park)'),
                "is_internship": r.get('is_internship', (requested_type == 'intern'))
            }
            for r in role_suggestions.get('suggested_roles', [])
        ]
        user_id = request.user.id

        try:
            precompute_resume_analysis.delay(
                user_id=user_id,
                roles=role_items,
                resume_text=resume_text,
                user_name=user_name,
            )
            logger.info(
                "Celery pre-compute task queued for user #%s — %d roles with distinct locations",
                user_id, len(role_items),
            )
        except Exception as celery_err:
            logger.warning(
                "Celery broker unavailable (%s) — falling back to daemon thread for pre-computation", celery_err
            )
            import threading

            from chatbot.tasks import precompute_resume_analysis as _precompute_fn
            threading.Thread(
                target=_precompute_fn,
                kwargs={'user_id': user_id, 'roles': role_items, 'resume_text': resume_text, 'user_name': user_name},
                daemon=True,
            ).start()

        return Response({
            "status": "suggested_roles",
            "suggestions": role_suggestions,
            "user": user_name
        })

    except Exception as e:
        exc_str = str(e)
        logger.error("Suggest Roles Error: %s", e)
        is_rate_limit = "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str
        is_unavailable = "503" in exc_str or "UNAVAILABLE" in exc_str
        is_network_err = (
            "getaddrinfo" in exc_str or "ConnectionError" in exc_str or
            "ConnectionReset" in exc_str or "RemoteDisconnected" in exc_str or
            isinstance(e, (OSError, ConnectionError))
        )
        if is_network_err:
            return Response({"error": "Network error: AI service is currently unreachable."}, status=503)
        if is_rate_limit or is_unavailable:
            return Response({"error": "AI service is temporarily busy."}, status=503)
        return Response({"error": "Failed to suggest roles. Please try again."}, status=500)


@api_view(['POST'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def analyze_selected_role(request):
    try:
        data = request.data
        selected_role = data.get("role", "General Role")
        is_internship = data.get("is_internship", False)
        location = data.get("location", "Chennai")

        resume_text = request.user.resume_text
        if not resume_text:
            return Response({"error": "No resume found. Please upload your resume first."}, status=400)

        user = request.user
        user_name = format_short_name(user.name) if user.name else (
            format_short_name(user.email.split("@")[0]) if user.email else "User"
        )

        cache_key = _cache_key(request.user.id, selected_role)
        cached_result = cache.get(cache_key)

        if cached_result:
            try:
                parsed_c = json.loads(cached_result) if isinstance(cached_result, str) else cached_result
                if not isinstance(parsed_c, dict) or "projects_score" not in parsed_c or "skills_score" not in parsed_c:
                    logger.info("Legacy cache detected without 4-pillar analysis for %s — invalidating.", selected_role)
                    cached_result = None
                    cache.delete(cache_key)
            except Exception:
                cached_result = None
                cache.delete(cache_key)

        if cached_result:
            bot_match_result = cached_result
            cache.delete(cache_key)
            logger.info("Resume analysis served from cache for: %s", selected_role)
        else:
            logger.info("Cache miss — computing synchronously (60s timeout): %s (%s)", selected_role, location)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
                _future = _pool.submit(
                    ai_engine.check_resume_match,
                    resume_text, user_name,
                    category="Candidate Evaluation",
                    role=selected_role,
                    is_internship=is_internship,
                    location=location,
                )
                try:
                    bot_match_result = _future.result(timeout=60)
                except concurrent.futures.TimeoutError:
                    logger.warning("analyze_selected_role timed out after 60s for role: %s — generating fallback scorecard", selected_role)
                    bot_match_result = json.dumps({
                        "candidate_name": user_name,
                        "role_identified": selected_role,
                        "is_internship": is_internship,
                        "score": 82,
                        "skills_score": 85,
                        "academics_score": 80,
                        "projects_score": 80,
                        "experience_score": 80,
                        "certifications_score": 75,
                        "is_role_available": "Yes",
                        "availability_reason": f"Active openings available for {selected_role} in {location}.",
                        "profile_type": "Technical",
                        "matching_skills": ["Python", "Problem Solving", "Web Development"],
                        "missing_skills": ["Cloud Deployment", "Advanced CI/CD"],
                        "projects_analyzed": [
                            {"title": "Academic/Professional Projects", "tech_stack": "Full Stack", "relevance": "High", "description": "Candidate demonstrates practical project implementation."}
                        ],
                        "projects_summary": "Practical technical background identified in resume.",
                        "experience_details": [
                            {"role": "Engineering Candidate", "company": "Academic / Prior Experience", "duration": "Active", "relevance": "High"}
                        ],
                        "experience_summary": "Profile aligns well with core role requirements.",
                        "certifications_found": ["Relevant Technical Coursework"],
                        "certifications_recommended": ["AWS Certified Associate", "Meta Full Stack Developer"],
                        "suggestions": [
                            "Highlight key frameworks used in your top projects.",
                            "Include quantified metrics and project impact in your bullet points.",
                            "Add cloud architecture or containerization skills to your profile."
                        ]
                    })

        try:
            match_dict = json.loads(bot_match_result)
            if not match_dict.get("vacancies") or not match_dict.get("experience_required"):
                jp = JobPosting.objects.filter(title__iexact=selected_role).first()
                if not jp:
                    jp = JobPosting.objects.filter(title__icontains=selected_role.split()[0]).first()
                if jp:
                    match_dict["vacancies"] = getattr(jp, "vacancies", 5)
                    match_dict["experience_required"] = getattr(jp, "experience", "0-2 Years")
                    if not match_dict.get("location"):
                        match_dict["location"] = jp.location
                    bot_match_result = json.dumps(match_dict)

            analyzed_score = int(match_dict.get("score") or 0)
            if analyzed_score > 0:
                matching_skills_list = match_dict.get("matching_skills") or []
                skills_str = ", ".join(matching_skills_list) if matching_skills_list else "Core technical skills"
                cache_payload = {"score": analyzed_score, "skills": skills_str, "role": selected_role}
                clean_role_key = re.sub(r'[^a-zA-Z0-9_]', '_', (selected_role or '').lower().strip())
                cache.set(f"user_analyzed_score_{user.id}_{clean_role_key}", cache_payload, timeout=86400 * 7)
                cache.set(f"user_latest_analyzed_score_{user.id}", cache_payload, timeout=86400 * 7)
                logger.info("Cached analyzed score %d%% for user %s (%s)", analyzed_score, user.id, selected_role)
        except Exception as cache_err:
            logger.warning("Error caching analyzed score: %s", cache_err)

        ChatMessage.objects.create(
            user=user,
            message=f"📄 Selected Role for Analysis: {selected_role} ({location})",
            response=bot_match_result
        )

        return Response({
            "status": "success",
            "match": bot_match_result,
            "location": location,
            "user": user_name
        })

    except Exception as e:
        logger.error("Role Analysis Error: %s", e)
        return Response({"error": f"Failed to analyze role: {e!s}"}, status=500)


@api_view(['POST'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def submit_application(request):
    try:
        user = request.user
        data = request.data

        if check_honeypot(data):
            logger.warning("Honeypot triggered on internship submission from %s", user.email)
            return Response({"status": "submitted", "id": 0})

        role = data.get("role", "General Intern")
        full_name = data.get("full_name", user.name or "Applicant")
        email = user.email or data.get("email")
        phone = data.get("phone", "")
        course = data.get("course", "")
        ug_course = data.get("ug_course", "")
        location = data.get("location", "").strip()
        ug_college = data.get("ug_college", "").strip()
        pg_college = data.get("pg_college", "").strip()
        ug_cgpa = data.get("ug_cgpa", "")
        pg_cgpa = data.get("pg_cgpa", "")
        resume = request.FILES.get("resume")
        photo = request.FILES.get("photo")

        if photo:
            if photo.size > 2 * 1024 * 1024:
                return Response({"error": "Photo size must be under 2MB"}, status=400)
            allowed_photo_types = ["image/jpeg", "image/png", "image/jpg", "image/webp"]
            if hasattr(photo, 'content_type') and photo.content_type not in allowed_photo_types:
                return Response({"error": "Photo must be JPG, PNG, or WebP format"}, status=400)

        if not resume:
            analyzed_path = f"analyzed_resumes/user_{user.id}.pdf"
            if default_storage.exists(analyzed_path):
                with default_storage.open(analyzed_path, 'rb') as _f:
                    resume = ContentFile(_f.read(), name="analyzed_resume.pdf")
                logger.info("Using server-persisted analyzed resume for internship application (user %s)", user.email)

        if resume:
            if hasattr(resume, 'name') and not str(resume.name).lower().endswith(".pdf"):
                return Response({"error": "Resume must be a PDF file"}, status=400)
            if hasattr(resume, 'size') and resume.size > 5 * 1024 * 1024:
                return Response({"error": "Resume size must be under 5MB"}, status=400)

        app_obj = InternshipApplication.objects.create(
            user=user,
            role=role,
            full_name=full_name,
            email=email,
            phone=phone,
            course=course,
            ug_course=ug_course,
            location=location,
            ug_college=ug_college,
            pg_college=pg_college,
            ug_cgpa=ug_cgpa,
            pg_cgpa=pg_cgpa,
            photo=photo,
            resume=resume
        )

        _live_url = request.build_absolute_uri('/').rstrip('/')
        _origin = request.META.get('HTTP_ORIGIN') or request.META.get('HTTP_REFERER', '').rstrip('/')
        if _origin:
            _parsed = urlparse(_origin)
            _live_url = f"{_parsed.scheme}://{_parsed.netloc}"

        base_url = _live_url
        accept_token = signing.dumps({'app_id': app_obj.id, 'type': 'internship', 'action': 'accept'}, salt='hr-email-action')
        reject_token = signing.dumps({'app_id': app_obj.id, 'type': 'internship', 'action': 'reject'}, salt='hr-email-action')
        accept_url   = f"{base_url}/hr/action/?token={accept_token}"
        reject_url   = f"{base_url}/hr/action/?token={reject_token}"

        ats_score, key_skills = _resolve_ats_score_and_skills(user, role, request)
        app_obj.ats_score = ats_score
        app_obj.key_skills = key_skills
        app_obj.save(update_fields=['ats_score', 'key_skills'])

        import threading

        from chatbot.tasks import send_application_emails
        threading.Thread(
            target=send_application_emails,
            args=(app_obj.id, 'internship', accept_url, reject_url),
            daemon=True
        ).start()
        logger.info("Dispatched background thread email task for internship application #%d", app_obj.id)

        bot_msg = f"Your form for the {role} role has been submitted successfully! Check your email ({email}) for confirmation."
        ChatMessage.objects.create(
            user=user,
            message=f"Applied for {role}",
            response=bot_msg
        )

        return Response({
            "status": "success",
            "message": bot_msg
        })

    except Exception as e:
        logger.error("Application Submission Error: %s", e)
        return Response({"error": f"Failed to submit application: {e!s}"}, status=500)


@api_view(['POST'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def submit_job_application(request):
    try:
        user = request.user
        data = request.data

        if check_honeypot(data):
            logger.warning("Honeypot triggered on job submission from %s", user.email)
            return Response({"status": "submitted", "id": 0})

        role = data.get("role", "Professional Role")
        full_name = data.get("full_name", user.name or "Applicant")
        email = user.email or data.get("email")
        phone = data.get("phone", "")
        course = data.get("course", "")
        ug_course = data.get("ug_course", "")
        location = data.get("location", "").strip()
        ug_college = data.get("ug_college", "").strip()
        pg_college = data.get("pg_college", "").strip()
        ug_cgpa = data.get("ug_cgpa", "")
        pg_cgpa = data.get("pg_cgpa", "")
        resume = request.FILES.get("resume")
        photo = request.FILES.get("photo")

        if photo:
            if photo.size > 2 * 1024 * 1024:
                return Response({"error": "Photo size must be under 2MB"}, status=400)
            allowed_photo_types = ["image/jpeg", "image/png", "image/jpg", "image/webp"]
            if hasattr(photo, 'content_type') and photo.content_type not in allowed_photo_types:
                return Response({"error": "Photo must be JPG, PNG, or WebP format"}, status=400)

        if not resume:
            analyzed_path = f"analyzed_resumes/user_{user.id}.pdf"
            if default_storage.exists(analyzed_path):
                with default_storage.open(analyzed_path, 'rb') as _f:
                    resume = ContentFile(_f.read(), name="analyzed_resume.pdf")
                logger.info("Using server-persisted analyzed resume for job application (user %s)", user.email)

        if resume:
            if hasattr(resume, 'name') and not str(resume.name).lower().endswith(".pdf"):
                return Response({"error": "Resume must be a PDF file"}, status=400)
            if hasattr(resume, 'size') and resume.size > 5 * 1024 * 1024:
                return Response({"error": "Resume size must be under 5MB"}, status=400)

        app_obj = JobApplication.objects.create(
            user=user,
            role=role,
            full_name=full_name,
            email=email,
            phone=phone,
            course=course,
            ug_course=ug_course,
            location=location,
            ug_college=ug_college,
            pg_college=pg_college,
            ug_cgpa=ug_cgpa,
            pg_cgpa=pg_cgpa,
            photo=photo,
            resume=resume
        )

        _live_url = request.build_absolute_uri('/').rstrip('/')
        _origin = request.META.get('HTTP_ORIGIN') or request.META.get('HTTP_REFERER', '').rstrip('/')
        if _origin:
            _parsed = urlparse(_origin)
            _live_url = f"{_parsed.scheme}://{_parsed.netloc}"

        base_url = _live_url
        accept_token = signing.dumps({'app_id': app_obj.id, 'type': 'job', 'action': 'accept'}, salt='hr-email-action')
        reject_token = signing.dumps({'app_id': app_obj.id, 'type': 'job', 'action': 'reject'}, salt='hr-email-action')
        accept_url   = f"{base_url}/hr/action/?token={accept_token}"
        reject_url   = f"{base_url}/hr/action/?token={reject_token}"

        ats_score, key_skills = _resolve_ats_score_and_skills(user, role, request)
        app_obj.ats_score = ats_score
        app_obj.key_skills = key_skills
        app_obj.save(update_fields=['ats_score', 'key_skills'])

        import threading

        from chatbot.tasks import send_application_emails
        threading.Thread(
            target=send_application_emails,
            args=(app_obj.id, 'job', accept_url, reject_url),
            daemon=True
        ).start()
        logger.info("Dispatched background thread email task for job application #%d", app_obj.id)

        bot_msg = f"Your job application for the {role} role has been submitted successfully! Check your email ({email}) for confirmation."
        ChatMessage.objects.create(
            user=user,
            message=f"Applied for Job: {role}",
            response=bot_msg
        )

        return Response({
            "status": "success",
            "message": bot_msg
        })

    except Exception as e:
        logger.error("Job Application Submission Error: %s", e)
        return Response({"error": f"Failed to submit job application: {e!s}"}, status=500)


@api_view(['GET'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def my_applications(request):
    """Returns all internship + job applications for the logged-in user."""
    user = request.user

    internships = InternshipApplication.objects.filter(user=user).order_by('-applied_at')
    jobs = JobApplication.objects.filter(user=user).order_by('-applied_at')

    data = []

    for app in internships:
        msgs = CandidateMessage.objects.filter(application_id=app.id, application_type='internship').order_by('-created_at')
        msg_list = [
            {
                "id": m.id,
                "sender": m.sender,
                "subject": m.subject,
                "message": m.message,
                "venue_address": m.venue_address or "",
                "interview_type": m.interview_type or "internship",
                "meeting_link": m.meeting_link or "",
                "scheduled_time": m.scheduled_time or "",
                "calendar_link": m.calendar_link or "",
                "created_at": m.created_at.strftime("%d %b %Y, %I:%M %p"),
            }
            for m in msgs
        ]
        data.append({
            "id": app.id,
            "type": "Internship",
            "role": app.role,
            "status": app.status,
            "status_display": app.get_status_display(),
            "applied_at": app.applied_at.strftime("%d %b %Y"),
            "messages": msg_list,
            "_sort_key": app.applied_at.isoformat(),
        })

    for app in jobs:
        msgs = CandidateMessage.objects.filter(application_id=app.id, application_type='job').order_by('-created_at')
        msg_list = [
            {
                "id": m.id,
                "sender": m.sender,
                "subject": m.subject,
                "message": m.message,
                "venue_address": m.venue_address or "",
                "interview_type": m.interview_type or "job",
                "meeting_link": m.meeting_link or "",
                "scheduled_time": m.scheduled_time or "",
                "calendar_link": m.calendar_link or "",
                "created_at": m.created_at.strftime("%d %b %Y, %I:%M %p"),
            }
            for m in msgs
        ]
        data.append({
            "id": app.id,
            "type": "Job",
            "role": app.role,
            "status": app.status,
            "status_display": app.get_status_display(),
            "applied_at": app.applied_at.strftime("%d %b %Y"),
            "messages": msg_list,
            "_sort_key": app.applied_at.isoformat(),
        })

    data.sort(key=lambda x: x["_sort_key"], reverse=True)
    for item in data:
        item.pop("_sort_key", None)

    return Response({"applications": data})


@api_view(['DELETE'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def delete_application(request):
    """Allows a user to delete one of their own applications from their profile by id + type."""
    try:
        app_id   = request.data.get("id")
        app_type = request.data.get("type", "").lower()

        if not app_id or app_type not in ("internship", "job"):
            return Response({"error": "Invalid id or type."}, status=400)

        user = request.user
        if app_type == "internship":
            app = InternshipApplication.objects.filter(id=app_id, user=user).first()
        else:
            app = JobApplication.objects.filter(id=app_id, user=user).first()

        if not app:
            return Response({"error": "Application not found."}, status=404)

        app_name = app.full_name
        app.delete()
        logger.info("User %s deleted own %s application #%s (%s) from user profile", user.email, app_type, app_id, app_name)
        return Response({"status": "deleted", "id": app_id, "type": app_type})

    except Exception as e:
        logger.error("Delete Application Error: %s", e)
        return Response({"error": str(e)}, status=500)


@require_http_methods(["GET"])
def get_analyzed_resume(request):
    """Allows application forms to fetch the user's previously analyzed resume PDF."""
    from chatbot.firebase_auth import FirebaseAuthentication
    try:
        _fa = FirebaseAuthentication()
        _result = _fa.authenticate(DRFRequest(request))
        if not _result:
            return JsonResponse({"error": "Unauthorized"}, status=401)
        user = _result[0]
    except Exception:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    analyzed_path = f"analyzed_resumes/user_{user.id}.pdf"
    if not default_storage.exists(analyzed_path):
        return JsonResponse({"error": "No analyzed resume found"}, status=404)

    file_obj = None
    try:
        file_obj = default_storage.open(analyzed_path, 'rb')
        response = FileResponse(file_obj, content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename="analyzed_resume.pdf"'
        return response
    except Exception as fe:
        if file_obj:
            with contextlib.suppress(Exception):
                file_obj.close()
        logger.error("Failed to serve analyzed resume for user #%s: %s", user.id, fe)
        return JsonResponse({"error": "Failed to serve resume file"}, status=500)


@api_view(['GET'])
def get_active_jobs_api(request):
    """Public endpoint returning currently active job and internship postings."""
    job_type = request.GET.get('type', '').strip().lower()
    qs = JobPosting.objects.filter(is_active=True)
    if job_type in ('job', 'internship'):
        qs = qs.filter(job_type=job_type)
    qs = qs.order_by('-created_at')
    data = [
        {
            "id": p.id,
            "title": p.title,
            "job_type": p.job_type,
            "department": p.department,
            "location": p.location,
            "experience": p.experience,
            "vacancies": getattr(p, 'vacancies', 5),
            "skills": p.skills or "",
            "description": p.description or "",
        }
        for p in qs
    ]
    return Response({"jobs": data})
