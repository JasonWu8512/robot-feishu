import json

import redis
import requests
from django import http
from django.conf import settings

from kevin.core import Kevin
from kevin.endpoints.management.models import Account
from kevin.events import CommandEvent


@Kevin.command(
    Kevin("mock")
    .arg("--env", "-e", default="dev")
    .arg("--activate", "-a", choices=["true", "false"])
    .arg("--domains", "-d", nargs="+", default=["api.pingxx.com"], choices=["api.pingxx.com"])
    .arg("--servers", "-s", nargs="+", default=["payatom", "交易中台"], choices=["payatom", "交易中台"])
)
def get_mock(event: CommandEvent):
    """ 获取mock状态 """
    url = "https://zero.jiliguala.com/v1"
    env = event.options.env
    activate = event.options.activate
    domains = event.options.domains
    servers = event.options.servers

    # 设置mock
    if activate:
        body = {
            "domains": {domain: json.loads(activate) for domain in domains},
            "server_list": servers,
            "env": env,
            "user_email": Account.objects.get(lark_open_id=event.open_id).email,
        }
        response = requests.post(f"{url}/mock/status/update", json=body).json()
        if response.get("msg") != "ok":
            return event.reply_text(str(response))
        else:
            return http.JsonResponse({"message": "ok"})

    # 获取mock
    response = requests.get(f"{url}/mock/status?env={env}").json()["data"]
    domain_status = ""
    is_mock = False
    for domains in response:
        is_mock = domains["status"]
        domain_status += f"【{env}】环境的mock被{'打开' if is_mock else '关闭'}了！"
        domain_status += f'\n【{domains["domain"]} : {is_mock}】'
        for servers in domains["details"]:
            domain_status += f'\n{servers["server"]} : {servers["status"]}'

    redis_client = redis.from_url(settings.REDIS_URL)
    redis_key = f"feishu:{settings.ZERO_VERIFY_TOKEN}:open_id"
    if event.token == settings.ZERO_VERIFY_TOKEN:
        redis_client.set(redis_key, event.open_id)
        # 打开mock后服务要重启，大概30S左右
        domain_status += f"\n当前消息为自动推送，因{'打开' if is_mock else '关闭'}mock后服务需重启，需等待大概30S"

    open_id = redis_client.get(redis_key)
    domain_status += f'\n<at user_id="{open_id.decode()}"></at>' if open_id else ""
    if domain_status:
        return event.reply_text(domain_status)
    else:
        return event.error("暂没查到mock相关状态")
