import json
import logging
from datetime import datetime

import requests

import kevin.settings
from kevin.core import Bot
from kevin.endpoints import lark as _lark
from kevin.endpoints.management.models import Account, Department, DepartmentAccount
from kevin.events import LarkApprovalEvent
from kevin.utils import SmtpMail

api = logging.getLogger("api")


@Bot.command(Bot("user_add"))
def handle(event: LarkApprovalEvent):
    res = user_address_book(event)
    if res is not None:
        note_str = f"你好，您的jira账号已经创建完毕。账号:{res},密码：123456，访问地址{kevin.settings.JIRA_URL}。"
        SmtpMail.send_email("qa_develop@jiliguala.com", "oPASmMZHLOHZkTkg", [f"{res}@jiliguala.com"], note_str)
        return event.reply_text(note_str)
    return event


@Bot.command(Bot("user_update"))
def handle(event: LarkApprovalEvent):
    res = user_address_book(event)
    if res is not None:
        note_str = f"你好，您的jira账号已经创建完毕。账号:{res},密码：123456，访问地址{kevin.settings.JIRA_URL}。"
        SmtpMail.send_email("qa_develop@jiliguala.com", "oPASmMZHLOHZkTkg", [f"{res}@jiliguala.com"], note_str)
        return event.reply_text(note_str)
    return event


@Bot.command(Bot("user_status_change"))
def handle(event: LarkApprovalEvent):
    user_address_book(event)
    return event


def user_address_book(event):
    lark = _lark.lark

    lark_users = {}
    department_info = {}
    users = lark.get_user(open_id=event.open_id).get("user")
    # 离职处理流程
    if users.get("status", {}).get("is_resigned"):
        return user_leave(users)
    for department_id in users.get("department_ids", []):
        detail = lark.get_department_detail(department_id).get("department", {})
        # 部门详情接口补充parent_open_department_id字段
        detail.update({"parent_open_department_id": detail["parent_department_id"]})
        _lark.user_department_info(
            lark_users=lark_users, department_info=department_info, users=[users], department=detail
        )

        # 部门信息扩展父子关系链，逻辑是获取父部门信息时不返回父部门字段或者父部门字段与当前部门相同
        parent_detail = lark.get_department_detail(detail["parent_department_id"]).get("department", {})

        while parent_detail.get("parent_department_id"):
            parent_detail.update({"parent_open_department_id": parent_detail["parent_department_id"]})
            # 更新部门信息链
            department_info.update({parent_detail["open_department_id"]: parent_detail})
            # 查询父部门的父部门信息
            parent_detail = lark.get_department_detail(parent_detail["parent_department_id"]).get("department", {})
            # 如果父部门的parent_department_id与父部门open_department_id相同代表是部门根节点，退出循环
            if parent_detail.get("parent_department_id") == parent_detail.get("open_department_id"):
                parent_detail.pop("parent_department_id")
    _lark.write_user_department_data(lark_users=lark_users, department_info=department_info)
    api.info(f"{event.open_id}的用户发生了{event.command_name}")
    if event.command_name != "user_status_change":
        # 技术部open_department_id
        tech_department_id = "od-6ac439ac289537cafd7d6e5cdff6a5e9"
        # 产品部open_department_id
        product_department_id = "od-e88a446342ff720acba17d4cc767f037"
        # 外部人员 outdoor_test_department_id 测试组
        outdoor_test_department_id = "od-7ecf56b605db0d5875d6d2ef91849c0b"
        lark_account_id = Account.objects.get(lark_open_id=event.open_id).id
        open_department_id = (
            DepartmentAccount.objects.filter(account_id=lark_account_id).order_by("-updated_at")[0].open_department_id
        )
        open_department_ids = Department.objects.get(open_department_id=open_department_id).parent_open_department_ids
        print(open_department_ids)
        api.info(f"{lark_account_id}对应的{open_department_ids}")
        if open_department_ids != "0":
            if (
                tech_department_id in open_department_ids
                or product_department_id in open_department_ids
                or outdoor_test_department_id == open_department_id
            ):
                return return_create_jira_info(users)
        else:
            if tech_department_id == open_department_id or product_department_id == open_department_id:
                return return_create_jira_info(users)


def user_leave(users):
    user_query = Account.objects.filter(lark_user_id=users.get("user_id"))
    DepartmentAccount.objects.filter(account_id__in=user_query).update(deactivated_at=datetime.now(), is_active=None)
    user_query.update(deactivated_at=datetime.now())


def create_jira_account(email_addr, display_name, account_name):
    user_api_url = "http://jira.jiliguala.com/rest/api/2/user"
    data = json.dumps(
        {"password": "123456", "emailAddress": email_addr, "displayName": display_name, "name": account_name}
    )
    headers = {"Authorization": "Basic YWNlX2JvdDpBZG1pbiFAIyQ=", "Content-Type": "application/json"}
    try:
        response = requests.post(user_api_url, data, headers=headers)
        if response.status_code != 201:
            logging.info(f"新增用户失败，失败原因{response.status_code}")
        return response.status_code
    except Exception as e:
        logging.error(e.message)


def return_create_jira_info(users):
    email_tmp = users["enterprise_email"]
    user_name_tmp = users["name"]
    if "@" in email_tmp:
        if not Account.objects.get(email=email_tmp).jira_name:
            account_name_tmp = email_tmp.split("@")[0]
            res_status = create_jira_account(email_tmp, user_name_tmp, account_name_tmp)
            if res_status == 201:
                return account_name_tmp
