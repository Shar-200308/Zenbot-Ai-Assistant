import logging
from collections import Counter

from django.db.models import Count, Sum
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from chatbot.firebase_auth import FirebaseAuthentication
from chatbot.models import InternshipApplication, JobApplication, JobPosting

from .hr_views import _is_hr

logger = logging.getLogger(__name__)


@api_view(['GET'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def hr_analytics_api(request):
    """
    Returns aggregated Business Intelligence & Visual Analytics data for the HR panel:
    - Funnel metrics (Total -> Under Review -> Shortlisted -> Selected / Rejected)
    - ATS score distribution & average talent score
    - Role & department application volume
    - Geographic / campus applicant distribution
    - Active openings & vacancy metrics

    BUG-11 fix: uses ORM aggregate() / annotate() for counts and averages instead
    of loading ALL application rows into Python memory on every request.
    Only role/location breakdowns (top-N) use Python-side Counter on minimal fields.
    """
    user = request.user
    if not _is_hr(user):
        return Response({'error': 'HR access required.'}, status=403)

    intern_qs = InternshipApplication.objects.filter(hr_archived=False, hr_deleted=False)
    job_qs    = JobApplication.objects.filter(hr_archived=False, hr_deleted=False)

    # ── Funnel counts via ORM (no Python-side row iteration) ──────────────────
    def _status_counts(qs):
        return {
            row['status']: row['cnt']
            for row in qs.values('status').annotate(cnt=Count('id'))
        }

    intern_status = _status_counts(intern_qs)
    job_status    = _status_counts(job_qs)

    status_counts = Counter(intern_status)
    status_counts.update(job_status)

    total_apps  = intern_qs.count() + job_qs.count()
    pending_cnt = status_counts.get('pending', 0)
    review_cnt  = status_counts.get('under_review', 0)
    short_cnt   = status_counts.get('shortlisted', 0)
    sel_cnt     = status_counts.get('selected', 0)
    rej_cnt     = status_counts.get('rejected', 0)

    selection_rate = round((sel_cnt / total_apps * 100), 1) if total_apps > 0 else 0.0
    actioned_count = review_cnt + short_cnt + sel_cnt + rej_cnt
    review_rate    = round((actioned_count / total_apps * 100), 1) if total_apps > 0 else 0.0

    # ── ATS average via ORM aggregate (no list comprehension) ─────────────────
    intern_agg = intern_qs.filter(ats_score__isnull=False).aggregate(
        total=Sum('ats_score'), cnt=Count('id')
    )
    job_agg = job_qs.filter(ats_score__isnull=False).aggregate(
        total=Sum('ats_score'), cnt=Count('id')
    )
    total_score_sum = (intern_agg['total'] or 0) + (job_agg['total'] or 0)
    total_score_cnt = (intern_agg['cnt'] or 0) + (job_agg['cnt'] or 0)
    avg_score = round(total_score_sum / total_score_cnt, 1) if total_score_cnt else 0.0

    # ── Score distribution via ORM COUNT per bracket (no Python iteration) ────
    score_brackets = {'< 70%': 0, '70% - 79%': 0, '80% - 89%': 0, '90% - 100%': 0}
    for qs in (intern_qs, job_qs):
        score_brackets['< 70%']      += qs.filter(ats_score__isnull=False, ats_score__lt=70).count()
        score_brackets['70% - 79%']  += qs.filter(ats_score__gte=70, ats_score__lt=80).count()
        score_brackets['80% - 89%']  += qs.filter(ats_score__gte=80, ats_score__lt=90).count()
        score_brackets['90% - 100%'] += qs.filter(ats_score__gte=90).count()

    # ── Top roles — annotate by role, only fetch 'role' + count columns ───────
    role_counts: Counter = Counter()
    for qs in (intern_qs, job_qs):
        for row in qs.values('role').annotate(cnt=Count('id')):
            role_counts[(row['role'] or 'Unassigned').strip()] += row['cnt']
    top_roles = [{"role": r, "count": c} for r, c in role_counts.most_common(8)]

    # ── Top locations — annotate by location, only fetch 'location' + count ───
    loc_counts: Counter = Counter()
    for qs in (intern_qs, job_qs):
        for row in qs.values('location').annotate(cnt=Count('id')):
            loc = (row['location'] or '').strip()
            loc_clean = loc.split(',')[0].strip() if ',' in loc else (loc or 'Other')
            loc_counts[loc_clean] += row['cnt']
    top_locations = [{"location": loc_name, "count": count} for loc_name, count in loc_counts.most_common(6)]

    # ── Active postings ───────────────────────────────────────────────────────
    active_postings = JobPosting.objects.filter(is_active=True)
    total_vacancies = active_postings.aggregate(total=Sum('vacancies'))['total'] or 0

    return Response({
        "status": "success",
        "kpis": {
            "total_candidates": total_apps,
            "selected_count": sel_cnt,
            "selection_rate": selection_rate,
            "review_rate": review_rate,
            "average_ats_score": avg_score,
            "active_openings": active_postings.count(),
            "total_vacancies": total_vacancies,
        },
        "funnel": {
            "total": total_apps,
            "pending": pending_cnt,
            "under_review": review_cnt,
            "shortlisted": short_cnt,
            "selected": sel_cnt,
            "rejected": rej_cnt,
        },
        "type_split": {
            "internships": intern_qs.count(),
            "jobs": job_qs.count(),
        },
        "score_distribution": score_brackets,
        "roles_distribution": top_roles,
        "locations_distribution": top_locations,
    })
