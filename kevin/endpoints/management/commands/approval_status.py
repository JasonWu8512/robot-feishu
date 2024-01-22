import json
import logging

from django import http

from kevin.core import Bot
from kevin.endpoints import lark as _lark
from kevin.endpoints.management.commands.approval_enum import ApprovalStatusEnum
from kevin.endpoints.management.models import Account, Department, DepartmentAccount, LarkCallback
from kevin.events import CommandEvent

api = logging.getLogger("api")


@Bot.command(Bot("approval_status").arg("--status", "-s", help="审批流状态").arg("--instance_code", "-i", help="审批流实例code"))
def handle(event: CommandEvent):
    """ 更新审批流状态 """
    status = event.options.status
    instance_code = event.options.instance_code
    approval_code = LarkCallback.objects.get(instance_code=instance_code, callback_type="approval_task").approval_code

    lark = _lark.lark
    lark_card = _lark.LarkCard

    detail = lark.get_instance_detail(instance_code=instance_code)
    task_id = detail.get("task_list")[0].get("id")
    if status == ApprovalStatusEnum.APPROVED.value:
        msg = lark.approval_approve(
            approval_code=approval_code, instance_code=instance_code, user_id=event.user_id, task_id=task_id
        )
    elif status == ApprovalStatusEnum.REJECTED.value:
        msg = lark.approval_reject(
            approval_code=approval_code, instance_code=instance_code, user_id=event.user_id, task_id=task_id
        )
    elif status == ApprovalStatusEnum.CANCELED.value:
        msg = lark.approval_cancel(
            approval_code=approval_code, instance_code=instance_code, user_id=event.user_id, task_id=task_id
        )
    else:
        return event.reply_http(message=f"不支持当前审批流类型", status=http.HttpResponseBadRequest.status_code)

    if msg.get("code") == 0:
        # 审批流被驳回转发给测试leader
        if status == ApprovalStatusEnum.CANCELED.value:
            tester = Account.objects.get(lark_user_id=event.user_id)
            developer = Account.objects.get(lark_user_id=detail["user_id"])
            department_name = Department.objects.get(
                open_department_id=DepartmentAccount.objects.get(
                    account_id=developer.id, is_active=True
                ).open_department_id
            ).name
            header = lark_card.header(content=f"{developer.name}的{detail['approval_name']}被{tester.name}拒绝")
            form = "".join([f"{i['name']}:  {i['value']}\n" for i in json.loads(detail["form"])])
            elements = [
                lark_card.divider(),
                lark_card.content(content=f"**申请人**\n{lark_card.at(developer.lark_user_id)} {department_name}"),
                lark_card.content(content=f"**审批事由**\n{form}"),
                lark_card.action(actions=[lark_card.approval_detail_button(instance_code=instance_code)]),
            ]
            card_data = lark_card.card(header=header, elements=elements)
            # 测试leader
            event.open_id = "ou_55cf8c34f9f7e2909bac242636db483c"
            _lark.reply(event.reply_card(message=card_data))
        return event.reply_http(message=msg.get("msg"))
    else:
        return event.reply_http(message=msg.get("msg"), status=http.HttpResponseBadRequest.status_code)
