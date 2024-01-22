from django import http
from django.conf import settings
from django.contrib import admin
from django.urls import path, re_path
from django.views import static

from kevin.endpoints import lark, sonar, webhook
from kevin.views import show_web

urlpatterns = [
    path("admin/", admin.site.urls),
    re_path(r"^static/(?P<path>.*)$", static.serve, {"document_root": settings.STATIC_ROOT}, name="static"),
    path("endpoints/webhook/<webhook_type>/", webhook.handle),
    path("endpoints/lark/", lark.handle),
    path("web/", show_web),
    path("", lambda x: http.JsonResponse({"message": "ok"})),
    path("sonar", sonar.handle),
    # path("endpoints/ding_talk/", admin.site.urls),
    # path("endpoints/wechat_web/", admin.site.urls),
]
