import logging
from datetime import datetime

import hutils

from kevin.core import Bot
from kevin.endpoints import lark as _lark
from kevin.endpoints.management.commands.approval_enum import ApprovalEnum
from kevin.endpoints.management.models import Account, LarkCallback
from kevin.events import LarkApprovalEvent

api = logging.getLogger("api")


@Bot.command(Bot("approval_instance"))
def handle(event: LarkApprovalEvent):
    lark = _lark.lark

    if event.approval_code in ApprovalEnum.values():
        data = lark.get_instance_detail(instance_code=event.instance_code)
        account = Account.objects.get(lark_user_id=data["user_id"])
        name, status, form, start_time, event.user_id, event.open_id = hutils.get_data(
            data, "approval_name", "status", "form", "start_time", "user_id", "open_id"
        )
        format_time = datetime.strftime(datetime.fromtimestamp(start_time / 1000), "%Y-%m-%d %H:%M:%S")
        event.user_id = data["user_id"]
        api.info(f"\n【审批】{name}\n时间: {format_time}\n收到: {account.name}({account.email})\n内容: {form}")
        LarkCallback.objects.update_or_create(
            instance_code=event.instance_code,
            callback_type=event.command_name,
            defaults={
                "approval_code": event.approval_code,
                "approval_name": name,
                "status": status,
                "user_id": data["user_id"],
                "user_name": account.name,
                "form": form,
            },
        )
    return event
