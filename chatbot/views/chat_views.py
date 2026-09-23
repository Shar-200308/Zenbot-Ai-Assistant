import json as _json
import logging

from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request as DRFRequest
from rest_framework.response import Response

from chatbot.ai import ai_engine
from chatbot.firebase_auth import FirebaseAuthentication
from chatbot.models import ChatMessage
from chatbot.services import ChatAnonRateThrottle, ChatRateThrottle

from .common import format_short_name

logger = logging.getLogger(__name__)


def chat_page(request):
    return render(request, "chatbot.html")


@api_view(['POST'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def save_chat(request):
    data = request.data
    ChatMessage.objects.create(
        user=request.user,
        message=data.get("message", ""),
        response=data.get("response", "")
    )
    return Response({"status": "chat_saved"})


@api_view(['GET'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def get_chats(request):
    try:
        page = max(1, int(request.query_params.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        page_size = max(1, min(int(request.query_params.get('page_size', 50)), 200))
    except (ValueError, TypeError):
        page_size = 50

    total = ChatMessage.objects.filter(user=request.user).count()
    offset = (page - 1) * page_size
    chats = ChatMessage.objects.filter(user=request.user).order_by('-created_at')[offset:offset + page_size]

    chat_data = [
        {
            "message": chat.message,
            "response": chat.response,
            "time": chat.created_at.strftime("%Y-%m-%d %H:%M")
        }
        for chat in reversed(list(chats))
    ]

    return Response({
        "chats": chat_data,
        "pagination": {
            "page": page, "page_size": page_size,
            "total": total, "total_pages": max(1, (total + page_size - 1) // page_size),
        }
    })


@api_view(['POST'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
def clear_history(request):
    ChatMessage.objects.filter(user=request.user).delete()
    return Response({"status": "history_cleared"})


@require_http_methods(["GET"])
def streaming_chat_api(request):
    """
    SSE streaming endpoint for the chatbot.
    Uses Django's StreamingHttpResponse — compatible with any WSGI server.
    GET /chat/stream/?message=<text>

    Disadvantage #4 fix: manual throttle check using ChatAnonRateThrottle (5/min per IP).
    SSE is a plain Django view (not DRF), so throttle_classes decorator cannot be used;
    we instantiate the throttle and check it manually instead.
    """
    # Manual throttle check for SSE (non-DRF endpoint)
    _throttle = ChatAnonRateThrottle()
    from rest_framework.request import Request as _DRFReq
    _drf_req = _DRFReq(request)
    if not _throttle.allow_request(_drf_req, None):
        return JsonResponse(
            {'error': 'Too many requests. Please slow down (5 messages/min limit).'},
            status=429,
        )
    try:
        _fa = FirebaseAuthentication()
        _result = _fa.authenticate(DRFRequest(request))
        if not _result:
            return JsonResponse({"error": "Unauthorized"}, status=401)
        user = _result[0]
    except Exception:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    message = request.GET.get("message", "").strip()
    if not message:
        return JsonResponse({"error": "Message required"}, status=400)

    user_name = format_short_name(user.name) if user.name else (
        format_short_name(user.email.split("@")[0]) if user.email else "User"
    )

    recent_chats = ChatMessage.objects.filter(user=user).order_by("-created_at")[:5]
    conversation_history = []
    for chat in reversed(recent_chats):
        conversation_history.append({"role": "user", "content": chat.message})
        conversation_history.append({"role": "bot", "content": chat.response})

    def event_stream():
        full_chunks = []
        try:
            for chunk in ai_engine.gemini_response_stream(message, user_name, conversation_history):
                full_chunks.append(chunk)
                yield f"data: {_json.dumps({'chunk': chunk, 'user': user_name})}\n\n"
        except Exception as exc:
            logger.error("SSE streaming error: %s", exc)
            yield f"data: {_json.dumps({'error': 'Stream interrupted. Please retry.'})}\n\n"

        full_response = "".join(full_chunks)
        if full_response:
            try:
                ChatMessage.objects.create(user=user, message=message, response=full_response)
            except Exception as db_err:
                logger.warning("Failed to save streamed chat to DB: %s", db_err)

        yield f"data: {_json.dumps({'done': True, 'user': user_name})}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    response["Access-Control-Allow-Origin"] = "*"
    return response


@api_view(['POST'])
@authentication_classes([FirebaseAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([ChatRateThrottle])  # Disadvantage #4 fix: 20 msg/min per user
def chat_api(request):
    try:
        data = request.data
        message = data.get("message", "").strip()

        if not message:
            return Response({"error": "Message required"}, status=400)

        user = request.user
        user_name = format_short_name(user.name) if user.name else (
            format_short_name(user.email.split("@")[0]) if user.email else "User"
        )

        recent_chats = ChatMessage.objects.filter(user=user).order_by("-created_at")[:5]
        conversation_history = []
        for chat in reversed(recent_chats):
            conversation_history.append({"role": "user", "content": chat.message})
            conversation_history.append({"role": "bot", "content": chat.response})

        bot_response = ai_engine.gemini_response(message, user_name, conversation_history=conversation_history)

        ChatMessage.objects.create(
            user=user,
            message=message,
            response=bot_response
        )

        return Response({
            "reply": bot_response,
            "user": user_name
        })

    except Exception as e:
        logger.error("Chat API Error: %s", e)
        return Response({"error": "Server error"}, status=500)
