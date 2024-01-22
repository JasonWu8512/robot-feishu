# -*- coding: utf-8 -*-
# @Time    : 2021/3/10 4:33 下午
# @Author  : zoey
# @File    : middleware.py
# @Software: PyCharm
import json
import logging


class ApiLoggingMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response
        self.apiLogger = logging.getLogger("api")

    def __call__(self, request):
        try:
            body = json.loads(request.body)
        except Exception:
            body = dict()
        body.update(dict(request.POST))
        response = self.get_response(request)
        response["Accept"] = "*/*"
        response["Access-Control-Allow-Headers"] = "*"
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS, DELETE, PATCH, PUT"
        response["Access-Control-Allow-Credentials"] = "true"
        if hasattr(response, "data"):
            self.apiLogger.info(
                "请求ip:{} {} {}  请求body:{} 返回体:{} {}".format(
                    request.META.get("REMOTE_ADDR"),
                    request.method,
                    request.path,
                    body,
                    response.status_code,
                    response.data,
                )
            )
        else:
            self.apiLogger.info(
                "请求ip:{} {} {} {} {}".format(
                    request.META.get("REMOTE_ADDR"), request.method, request.path, body, response.status_code
                )
            )
        return response
