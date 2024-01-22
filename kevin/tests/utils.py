import json

import hutils
from django import http
from django.test import TestCase


class KevinTest(TestCase, hutils.TestCaseMixin):
    def send_text(self, message) -> http.HttpResponse:
        data = {"text": message, "username": "kevin"}
        response = self.client.post(
            "/endpoints/webhook/api/",
            data=json.dumps(data),
            content_type="application/json",
        )
        response.data = json.loads(response.content)
        return response
