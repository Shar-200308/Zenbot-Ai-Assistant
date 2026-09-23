import functools
import logging

import firebase_admin
from django.conf import settings
from django.http import JsonResponse
from firebase_admin import auth, credentials
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import FirebaseUser

logger = logging.getLogger(__name__)

# ================= FIREBASE INIT =================
if not firebase_admin._apps:
    cred = credentials.Certificate(settings.FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred)


# ================= VERIFY TOKEN =================
def verify_firebase_token(request):
    logger.debug("Entering verify_firebase_token")
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        logger.debug("Authorization header MISSING")
        # BUG-09 fix: do NOT log all headers — they may contain sensitive tokens
        return None

    # Expect: Authorization: Bearer <token>
    # BUG-08 fix: validate split result before indexing to prevent IndexError
    #             on malformed headers like "Bearer" (no token) or extra spaces.
    try:
        parts = auth_header.split(" ", 1)   # maxsplit=1 so spaces in token are safe
        if len(parts) != 2 or not parts[1].strip():
            logger.debug("Malformed Authorization header — expected 'Bearer <token>'")
            return None
        token = parts[1].strip()
        decoded_token = auth.verify_id_token(token, clock_skew_seconds=60)
        return decoded_token
    except Exception as e:
        # BUG-09 fix: truncate token in logs — never store full JWT in plaintext
        safe_token = (auth_header[:20] + "...") if len(auth_header) > 20 else auth_header
        logger.debug("Auth header (truncated): %s", safe_token)
        logger.debug("Token verification exception: %s", type(e).__name__)
        return None


# ================= DECORATOR =================
def firebase_login_required(view_func):
    @functools.wraps(view_func)  # ISS 1 fix: preserve view name for Django URL resolver
    def wrapper(request, *args, **kwargs):
        decoded = verify_firebase_token(request)

        if not decoded:
            return JsonResponse(
                {"error": "Unauthorized"},
                status=401
            )

        request.firebase_user = decoded
        return view_func(request, *args, **kwargs)

    return wrapper


# ================= DRF AUTHENTICATION =================
class FirebaseAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        decoded = verify_firebase_token(request)
        if not decoded:
            raise AuthenticationFailed("Invalid or expired Firebase token")

        uid = decoded.get("uid")
        email = decoded.get("email", "")
        name = decoded.get("name") or decoded.get("displayName") or ""

        if not name and email:
            name = email.split("@")[0].capitalize()

        if not uid:
             raise AuthenticationFailed("Firebase token missing UID")

        user, _ = FirebaseUser.objects.get_or_create(
            uid=uid,
            defaults={
                "email": email,
                "name": name,
                # BUG 1 fix: FirebaseUser has no 'role' field — removed to prevent TypeError on every login
            }
        )

        return (user, decoded)

    def authenticate_header(self, request):
        return 'Bearer'
