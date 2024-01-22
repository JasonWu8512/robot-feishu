import json
import logging

from django import http

from kevin.core import Bot
from kevin.endpoints import lark as _lark
from kevin.endpoints.management.commands.approval_enum import ApprovalEnum
from kevin.endpoints.management.models import Account, Chat, Department, DepartmentAccount, JiraProjectChat
from kevin.events import CommandEvent

api = logging.getLogger("api")


@Bot.command(Bot("packaging_test").arg("keyword", help="提测需求表单"))
def handle(event: CommandEvent):
    """ 开发打包测试 """
    keyword = json.loads(event.options.keyword)
    # 开发提测审批流表单顺序是固定的
    instance_form_keys = [
        keyword.get("name"),  # 提测需求名称
        keyword.get("summary"),  # 技术概要链接
        keyword.get("influence"),  # 影响范围
        keyword.get("server"),  # 前后端提测服务
        keyword.get("result"),  # 冒烟结果
        # keyword.get("review"), # 复核冒烟结果
        keyword.get("postpone"),  # 是否延期
        keyword.get("reason"),  # 延期原因
    ]
    owner_email = keyword.get("owner_email")
    reject_count = keyword.get("reject_count")
    jira_projects = keyword.get("jira_projects")
    approval_code = ApprovalEnum.MentionDirectorDeveloped.value if reject_count else ApprovalEnum.MentionDeveloped.value

    lark = _lark.lark

    approval_detail = lark.get_approval_detail(approval_code=approval_code)
    check_node_id = leader_check_node_id = ""
    for node in approval_detail.get("node_list"):
        if node.get("name") == "审批":
            check_node_id = node.get("node_id")
        if node.get("name") == "总监审批":
            leader_check_node_id = node.get("node_id")

    # 填充用户的leader
    owner_open_id = Account.objects.get(email=owner_email).lark_open_id
    leader_open_ids = []
    for open_id in [event.open_id, owner_open_id]:
        try:
            account_id = Account.objects.get(lark_open_id=open_id).id
            department_id = DepartmentAccount.objects.get(account_id=account_id).open_department_id
            leader_id = Department.objects.get(open_department_id=department_id).leader_id
            while not leader_id:
                try:
                    department_id = Department.objects.get(open_department_id=department_id).parent_open_department_id
                    leader_id = Department.objects.get(open_department_id=department_id).leader_id
                except Department.DoesNotExist:
                    break
            leader_open_ids.append(Account.objects.get(id=leader_id).lark_open_id)
        except (Account.DoesNotExist, Department.DoesNotExist, DepartmentAccount.DoesNotExist):
            pass
    # 实际抄送人员需去重
    cc_open_ids = list(set(leader_open_ids))
    # 总监确认的审批流需要固定抄送给卢成和测试同学,不需要抄送给开发的leader
    if reject_count:
        cc_open_ids = leader_open_ids[1:]
        cc_open_ids.append("ou_55cf8c34f9f7e2909bac242636db483c")
        cc_open_ids.append(event.open_id)
        cc_open_ids = list(set(cc_open_ids))

    form = json.loads(approval_detail.get("form"))
    for index, form_data in enumerate(form):
        value = instance_form_keys[index]
        if "option" in form_data:
            for i in form_data.get("option"):
                if value == i.get("text"):
                    value = i.get("value")
                    break
        form_data.update({"value": value})
    msg = lark.create_approval_instance(
        approval_code=approval_code,
        open_id=event.open_id,
        open_id_list={check_node_id: [owner_open_id], leader_check_node_id: [leader_open_ids[0]]},
        form=form,
    )

    if not msg.get("msg"):
        instance_code = msg.get("data").get("instance_code")
        cc_msg = lark.create_approval_cc(
            approval_code=approval_code, instance_code=instance_code, open_id=event.open_id, cc_open_ids=cc_open_ids
        )
        if not cc_msg.get("msg"):
            # 开发提测总监确认审批流提交成功后需要通知到群
            if reject_count:
                try:
                    for jira_project in jira_projects:
                        chat_id = JiraProjectChat.objects.get(project=jira_project, is_active=True).chat_id
                        event.chat_id = Chat.objects.get(id=chat_id).chat_id
                        form = json.loads(approval_detail.get("form"))
                        [form_data.update({"value": instance_form_keys[index]}) for index, form_data in enumerate(form)]
                        card = card_msg(keyword, event.open_id, leader_open_ids[0], form)
                        _lark.reply(event.reply_card(card))
                except JiraProjectChat.DoesNotExist:
                    pass
            return event.reply_http(message=instance_code, status=http.HttpResponse.status_code)
        else:
            return event.reply_http(
                message=f'审批创建成功，抄送失败原因：{cc_msg.get("msg")}', status=http.HttpResponseBadRequest.status_code
            )
    else:
        return event.reply_http(message=msg.get("msg"), status=http.HttpResponseBadRequest.status_code)


def card_msg(keyword, dev_open_id, leader_open_id, form):
    dev_name = Account.objects.get(lark_open_id=dev_open_id).name
    dev_leader_name = Account.objects.get(lark_open_id=leader_open_id).name
    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": "**计划名称：**"}},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"[{keyword.get('name')}]($urlVal)",
                "href": {"urlVal": {"url": "http://qa.jiliguala.com/#/testTrack/testCasePlan/smoke/list"}},
            },
        },
        {"tag": "div", "text": {"tag": "lark_md", "content": "**方向：**"}},
        {"tag": "div", "text": {"tag": "lark_md", "content": f"{dev_name} -> {dev_leader_name}"}},
        {"tag": "div", "text": {"tag": "lark_md", "content": "**表单内容：**"}},
    ]
    for data in form:
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": f"{data.get('name')}：{data.get('value') or '无'}"}},
        )
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"<at id={leader_open_id}></at>"}})

    return {
        "config": {"wide_screen_mode": True, "enable_forward": True},
        "header": {
            "title": {"tag": "lark_md", "content": f"开发提测(总监确认)审批提交通知"},
            "template": "violet",
        },
        "elements": elements,
    }
