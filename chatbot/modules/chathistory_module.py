import logging

from chatbot.models import ChatMessage

logger = logging.getLogger(__name__)


class ChatHistoryModule:

    def save_message(self, user_message: str, bot_reply: str):
        ChatMessage.objects.create(message=user_message, response=bot_reply)

    def get_last_messages(self, limit=20):
        return ChatMessage.objects.all().order_by('-id')[:limit]
