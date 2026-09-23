import logging

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from chatbot.firebase_auth import FirebaseAuthentication
from chatbot.services import is_hr_email

from .common import format_short_name

logger = logging.getLogger(__name__)


def login_page(request):
    return render(request, "login.html")


def signup_page(request):
    return render(request, "signup.html")


def profile_page(request):
    return render(request, "profile.html")


@api_view(['POST', 'GET', 'OPTIONS'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def save_user(request):
    user = request.user
    return Response({
        "status": "user_saved",
        "userName": format_short_name(user.name),
        "userEmail": user.email,
        "is_hr": is_hr_email(user.email) or getattr(user, 'role', None) in ('hr', 'admin'),
    })


def health_check(request):
    """
    Disadvantage #5 fix: /health/ endpoint for load balancers, uptime monitors,
    and Kubernetes liveness / readiness probes.

    Returns HTTP 200 if all critical services are reachable,
    HTTP 503 if any critical service is down.
    """
    status = {}
    http_status = 200

    # ── Database check ─────────────────────────────────────────────────────────
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        status["database"] = "ok"
    except Exception as e:
        status["database"] = f"error: {type(e).__name__}"
        http_status = 503

    # ── Cache check ────────────────────────────────────────────────────────────
    try:
        cache.set("_health_probe", "1", timeout=5)
        val = cache.get("_health_probe")
        status["cache"] = "ok" if val == "1" else "miss"
    except Exception as e:
        status["cache"] = f"error: {type(e).__name__}"
        # Cache failure is non-critical — don't return 503

    # ── Overall result ─────────────────────────────────────────────────────────
    status["status"] = "healthy" if http_status == 200 else "degraded"

    return JsonResponse(status, status=http_status)
