import argparse
import dataclasses
import datetime
import functools
from typing import AnyStr, List, Optional, Union

import hutils
from django import http

from kevin.endpoints.management.models import Account


class ReplyTypes(hutils.TupleEnum):
    NO_REPLY = "no_reply", "尚未回复"
    TEXT = "text", "文字回复"
    CARD = "card", "卡片回复"
    IMAGE = "image", "图片回复"
    ERROR = "error", "回复报错了"
    HTTP = "http", "回复请求"


@dataclasses.dataclass
class BaseEvent:
    endpoint: str = ""
    username: str = ""
    created_at: datetime.datetime = dataclasses.field(default_factory=datetime.datetime.now)
    reply_type: ReplyTypes = ReplyTypes.NO_REPLY
    reply_message: Union[str, dict] = ""
    http_status: http.HttpResponse.status_code = http.HttpResponse.status_code

    def reply_text(self, message: str):
        self.reply_type = ReplyTypes.TEXT
        self.reply_message = message
        return self

    def reply_card(self, message: dict):
        self.reply_type = ReplyTypes.CARD
        self.reply_message = message
        return self

    def reply_image(self, image_url: str):
        self.reply_type = ReplyTypes.IMAGE
        self.reply_message = image_url
        return self

    def error(self, message: Union[str, Exception]):
        self.reply_type = ReplyTypes.ERROR
        self.reply_message = f"Error:\n{message}"
        self.http_status = http.HttpResponseBadRequest.status_code
        return self

    def reply_http(self, message: str, status: http.HttpResponse.status_code = http.HttpResponse.status_code):
        self.reply_type = ReplyTypes.HTTP
        self.reply_message = message
        self.http_status = status
        return self

    @functools.cached_property
    def account(self) -> Account:
        return Account.objects.get(name=self.username)

    @functools.cached_property
    def account_name(self) -> Account:
        return self.account.jira_name


@dataclasses.dataclass
class LarkCommandEvent(BaseEvent):
    open_id: str = None  # 飞书用户open_id
    user_id: str = None  # 飞书用户user_id
    open_ids: List[AnyStr] = None  # 飞书用户user_id列表
    user_ids: List[AnyStr] = None  # 飞书用户user_id列表
    chat_id: str = None  # 飞书对话的chat_id
    token: str = ""  # 飞书token


@dataclasses.dataclass
class CommandEvent(LarkCommandEvent):
    command_name: str = ""  # 命令名称
    text: str = ""
    card: dict = dataclasses.field(default_factory=dict)
    options: Optional[argparse.Namespace] = None


@dataclasses.dataclass
class LarkApprovalEvent(CommandEvent):
    approval_code: str = ""  # 飞书审批定义 Code
    instance_code: str = ""  # 飞书审批实例 Code
