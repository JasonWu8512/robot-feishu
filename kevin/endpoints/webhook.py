import json

from django import http

from kevin.core import Endpoints


def handle(request: http.HttpRequest, webhook_type: str):
    if webhook_type not in ("api", "gitlab", "sentry"):
        return http.HttpResponseBadRequest("oh")
    data = json.loads(request.body)
    event = Endpoints.WEBHOOK.handle(data["text"], data["username"])
    return http.JsonResponse({"message": event.reply_message, "type": event.reply_type.value})
