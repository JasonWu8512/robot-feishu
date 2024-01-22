import base64
import hashlib
import io
import json
import logging
import random
import time
from copy import deepcopy
from datetime import datetime
from typing import Dict, List, Union
from uuid import uuid4

import hutils
import redis
import requests
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from django import http
from django.conf import settings
from django.views.decorators.http import require_http_methods
from pytz import timezone
from retry import retry

from kevin.celery import app
from kevin.core import Endpoints
from kevin.endpoints.management.commands.approval_enum import ApprovalEnum
from kevin.endpoints.management.models import Account, Department, DepartmentAccount
from kevin.events import BaseEvent, CommandEvent, LarkApprovalEvent, ReplyTypes

trace = logging.getLogger("trace")
api = logging.getLogger("api")


def user_department_info(lark_users, department_info, users, department):
    for user in users:
        phone = user.get("mobile", "")[3:]
        if not user.get("enterprise_email"):
            continue
        # 用户可能已经存在
        lark_users[user["enterprise_email"]] = lark_users.get(
            user["enterprise_email"],
            {
                "name": user["name"],
                "phone": phone,
                "open_id": user["open_id"],
                "user_id": user["user_id"],
                "status": user["status"]["is_activated"],
                "open_department_ids": [],
            },
        )
        # 员工-部门一对多
        lark_users[user["enterprise_email"]]["open_department_ids"].append(department["open_department_id"])

    # 查部门信息
    detail = lark.get_department_detail(department["open_department_id"]).get("department", {})
    # 发现飞书返回的parent_department_id和parent_open_department_id是一样的
    # 通过部门列表接口获取的数据有parent_open_department_id字段，通过部门详情接口的数据只有parent_department_id字段, 需补充
    # 全量同步飞书用户部门数据用部门列表接口，增量用户信息变更用部门详情接口
    detail.update({"parent_open_department_id": department.get("parent_open_department_id")})
    department_info[department["open_department_id"]] = detail


def write_user_department_data(lark_users, department_info):
    for open_department_id, detail in department_info.items():
        detail["parent_open_department_ids"] = detail["parent_open_department_id"]
        # 父部门详情
        parent_department_info = department_info.get(detail["parent_open_department_id"])
        while parent_department_info:
            # 获取父部门id
            parent_id = parent_department_info.get("parent_open_department_id")
            detail["parent_open_department_ids"] += f",{parent_id}"
            # 更新父部门详情
            parent_department_info = department_info.get(parent_id)

        try:
            leader = Account.objects.get(lark_open_id=detail.get("leader_user_id"))
            leader_id, leader_email = leader.id, leader.email
        except Account.DoesNotExist:
            leader_id = leader_email = None
        department, _ = Department.objects.update_or_create(
            open_department_id=open_department_id,
            defaults={
                "name": detail["name"],
                "department_id": detail["department_id"],
                "open_department_id": open_department_id,
                "parent_department_id": detail["parent_department_id"],
                "parent_open_department_id": detail["parent_open_department_id"],
                "parent_open_department_ids": detail["parent_open_department_ids"],
                "leader_id": leader_id,
                "leader_email": leader_email,
                "count": detail["member_count"],
            },
        )

    for email, data in lark_users.items():
        account, _ = Account.objects.update_or_create(
            lark_open_id=data["open_id"],
            defaults={
                "name": data["name"],
                "phone": data["phone"],
                "email": email,
                "lark_user_id": data["user_id"],
                "english_name": email.split("@")[0],
            },
        )

        for open_department_id in data["open_department_ids"]:
            DepartmentAccount.objects.update_or_create(
                account_id=account.id,
                open_department_id=open_department_id,
                defaults={"open_department_id": open_department_id},
            )

        # 批量写入员工是否在职
        DepartmentAccount.all_objects.filter(account_id=account.id).update(is_active=True)
    # 标记质量效能部的人员为QA
    open_department_id = "od-15df6c7b98cde121c4b39bf3c831eacb"
    users = lark.get_all_department_users(open_department_id=open_department_id)["user_list"]
    users_open_id = {user["open_id"] for user in users}
    lark_users_open_id = {lark_user["open_id"] for _, lark_user in lark_users.items()}
    for user_open_id in lark_users_open_id & users_open_id:
        Account.objects.update_or_create(lark_open_id=user_open_id, defaults={"user_role": "QA"})


@app.task()
def sync_lark_users():
    departments = lark.get_all_departments()["department_infos"]
    lark_users = {}
    department_info = {}
    for department in departments:
        # 查人员信息
        users = lark.get_all_users(department["open_department_id"]).get("items", [])
        user_department_info(lark_users=lark_users, department_info=department_info, users=users, department=department)
    lark.redis.set("lark_users", json.dumps(lark_users))
    lark.redis.set("department_info", json.dumps(department_info))


@app.task()
def write_lark_users():
    begin_at = datetime.now(tz=timezone(settings.TIME_ZONE)).strftime("%Y-%m-%d")
    DepartmentAccount.all_objects.filter(is_active=True).update(is_active=None)

    lark_users = json.loads(lark.redis.get("lark_users"))
    department_info = json.loads(lark.redis.get("department_info"))
    write_user_department_data(lark_users=lark_users, department_info=department_info)

    # 删除失效员工和部门
    Account.objects.filter(updated_at__lt=begin_at).update(deactivated_at=datetime.now())
    Department.objects.filter(updated_at__lt=begin_at).update(deactivated_at=datetime.now())
    DepartmentAccount.objects.filter(updated_at__lt=begin_at).update(deactivated_at=datetime.now())


def subscribe_approval():
    for approval in ApprovalEnum.values():
        lark.subscribe_approval(approval)


class LarkError(hutils.TupleEnum):
    SUCCESS = 0, "访问成功"
    FREQUENCY_LIMIT = 99991400, "访问频率限制"


class Lark:
    APPROVAL_HOST = "https://www.feishu.cn/approval/openapi/v2"

    def __init__(self):
        self.app_id = settings.LARK_APP_ID
        self.secret = settings.LARK_APP_SECRET
        self.redis = redis.from_url(settings.REDIS_URL)
        self.session = requests.Session()

    def decrypt(self, encrypted) -> dict:
        decrypt = base64.b64decode(encrypted)
        key = hashlib.sha256(settings.LARK_ENCRYPT_KEY.encode()).digest()
        cipher = Cipher(algorithms.AES(key), modes.CBC(decrypt[:16]))
        decryptor = cipher.decryptor()
        unpad = decryptor.update(decrypt[16:]) + decryptor.finalize()
        result = unpad[: -ord(unpad[len(unpad) - 1 :])].decode()
        return json.loads(result)

    def handle_data(self, data):
        # api.info(f"飞书原始推送：{data}")
        if data.get("encrypt"):
            data = self.decrypt(data["encrypt"])
        uuid = data.pop("uuid", uuid4().hex)
        if self.redis.exists(uuid):
            return {"message": "ok"}
        self.redis.setex(uuid, 86400, "1")
        if data.get("token", "") not in (settings.LARK_VERIFY_TOKEN, settings.ZERO_VERIFY_TOKEN):
            return {"message": "ok"}
        return data

    def send_text(self, open_id, user_id, chat_id, text, reply_message_id=""):
        return self._post(
            "/message/v4/send/",
            open_id=open_id,
            user_id=user_id,
            chat_id=chat_id,
            root_id=reply_message_id,
            msg_type="text",
            content={"text": text},
        )

    def send_card(self, open_id, user_id, chat_id, card, reply_message_id=""):
        return self._post(
            "/message/v4/send/",
            open_id=open_id,
            user_id=user_id,
            chat_id=chat_id,
            root_id=reply_message_id,
            msg_type="interactive",
            card=card,
        )

    def send_image(self, open_id, user_id, chat_id, image_key, reply_message_id=""):
        return self._post(
            "/message/v4/send/",
            open_id=open_id,
            user_id=user_id,
            chat_id=chat_id,
            root_id=reply_message_id,
            msg_type="image",
            content={"image_key": image_key},
        )

    def send_post(self, open_id, user_id, chat_id, title: str, content: list, reply_message_id=""):
        return self._post(
            "/message/v4/send/",
            open_id=open_id,
            user_id=user_id,
            chat_id=chat_id,
            root_id=reply_message_id,
            msg_type="post",
            content={"post": {"zh_cn": {"title": title, "content": content}}},
        )

    def batch_send_text(self, open_ids, user_ids, text):
        return self._post(
            "/message/v4/batch_send/",
            open_ids=open_ids,
            user_ids=user_ids,
            msg_type="text",
            content={"text": text},
        )

    def batch_send_card(self, open_ids, user_ids, card):
        return self._post(
            "/message/v4/batch_send/",
            open_ids=open_ids,
            user_ids=user_ids,
            msg_type="interactive",
            card=card,
        )

    def batch_send_image(self, open_ids, user_ids, image_key):
        return self._post(
            "/message/v4/batch_send/",
            open_id=open_ids,
            user_ids=user_ids,
            msg_type="image",
            content={"image_key": image_key},
        )

    def batch_send_post(self, open_ids, user_ids, title: str, content: list):
        return self._post(
            "/message/v4/batch_send/",
            open_ids=open_ids,
            user_ids=user_ids,
            msg_type="post",
            content={"post": {"zh_cn": {"title": title, "content": content}}},
        )

    def get_user(self, open_id: str, user_id_type="open_id"):
        return self._get(f"/contact/v3/users/{open_id}", user_id_type=user_id_type, get_data=True)

    def update_user(self, open_id: str, **kwargs):
        return self._post("/contact/v1/user/update", open_id=open_id, **kwargs)

    def delete_user(self, open_id):
        return self._post("/contact/v1/user/delete", open_id=open_id)

    def get_chats(self, page_token=None):
        return self._get("/chat/v4/list", page_size=200, get_data=True, page_token=page_token)

    def get_department_users(self, open_department_id, page_token=None):
        return self._get(
            "/contact/v1/department/user/list",
            department_id=open_department_id,
            page_size=100,
            get_data=True,
            page_token=page_token,
            fetch_child=True,
        )

    def get_users(self, open_department_id, page_token=None):
        return self._get(
            "/contact/v3/users",
            department_id=open_department_id,
            page_size=100,
            get_data=True,
            page_token=page_token,
        )

    def get_department_detail(self, department_id):
        return self._get(
            f"/contact/v3/departments/{department_id}",
            get_data=True,
        )

    def get_departments(self, page_token=None):
        return self._get(
            "/contact/v1/department/simple/list",
            open_department_id=0,
            fetch_child=True,
            page_size=100,
            get_data=True,
            page_token=page_token,
        )

    def get_all_users(self, open_department_id):
        _ = self.get_users(open_department_id)
        resp = deepcopy(_)
        while _["has_more"]:
            _ = self.get_users(open_department_id=open_department_id, page_token=_["page_token"])
            resp["items"] += _["items"]
        return resp

    def get_all_departments(self):
        _ = self.get_departments()
        resp = deepcopy(_)
        while _["has_more"]:
            _ = self.get_departments(page_token=_["page_token"])
            resp["department_infos"] += _["department_infos"]
        return resp

    def get_all_department_users(self, open_department_id):
        _ = self.get_department_users(open_department_id)
        resp = deepcopy(_)
        while _["has_more"]:
            _ = self.get_users(open_department_id=open_department_id, page_token=_["page_token"])
            resp["items"] += _["items"]
        return resp

    def get_all_chats(self):
        _ = self.get_chats()
        resp = deepcopy(_)
        while _["has_more"]:
            _ = self.get_chats(page_token=_["page_token"])
            resp["data"] += _["data"]
        return resp

    def get_instance_detail(self, instance_code):
        return self._post(f"{self.APPROVAL_HOST}/instance/get", get_data=True, instance_code=instance_code)

    def get_approval_detail(self, approval_code):
        return self._post(f"{self.APPROVAL_HOST}/approval/get", get_data=True, approval_code=approval_code)

    def create_approval_instance(self, approval_code, open_id, open_id_list, form):
        return self._post(
            f"{self.APPROVAL_HOST}/instance/create",
            approval_code=approval_code,
            open_id=open_id,
            node_approver_open_id_list=open_id_list,
            form=json.dumps(form),
        )

    def create_approval_cc(self, approval_code, instance_code, open_id, cc_open_ids, comment=None):
        return self._post(
            f"{self.APPROVAL_HOST}/instance/cc",
            approval_code=approval_code,
            instance_code=instance_code,
            open_id=open_id,
            cc_open_ids=cc_open_ids,
            comment=comment,
        )

    def approval_approve(self, approval_code, instance_code, user_id, task_id):
        return self._post(
            f"{self.APPROVAL_HOST}/instance/approve",
            approval_code=approval_code,
            instance_code=instance_code,
            user_id=user_id,
            task_id=task_id,
        )

    def approval_reject(self, approval_code, instance_code, user_id, task_id):
        return self._post(
            f"{self.APPROVAL_HOST}/instance/reject",
            approval_code=approval_code,
            instance_code=instance_code,
            user_id=user_id,
            task_id=task_id,
        )

    def approval_cancel(self, approval_code, instance_code, user_id, task_id):
        return self._post(
            f"{self.APPROVAL_HOST}/instance/cancel",
            approval_code=approval_code,
            instance_code=instance_code,
            user_id=user_id,
            task_id=task_id,
        )

    def subscribe_approval(self, approval_code):
        return self._post(f"{self.APPROVAL_HOST}/subscription/subscribe", approval_code=approval_code)

    def upload_image(self, url):
        image_file = io.BytesIO(self.session.get(url).content)
        response = requests.post(
            "https://open.feishu.cn/open-apis/image/v4/put/",
            headers={"Authorization": f"Bearer {self.access_token}"},
            files={"image": image_file},
            data={"image_type": "message"},
            stream=True,
        )
        data = response.json()
        return data["data"]["image_key"]

    @retry(tries=10, delay=1)
    def _get(self, path, get_data=False, **data):
        response = self.session.get(
            path if path.startswith("http") else "https://open.feishu.cn/open-apis" + path,
            headers={"Authorization": f"Bearer {self.access_token}"},
            params=data,
        )
        response.raise_for_status()
        data = response.json()
        return data["data"] if get_data else data

    @retry(tries=10, delay=1)
    def _post(self, path, get_data=False, **data):
        data = {k: v for k, v in data.items() if v}
        response = self.session.post(
            path if path.startswith("http") else "https://open.feishu.cn/open-apis" + path,
            headers={"Authorization": f"Bearer {self.access_token}"},
            json=data,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code") == LarkError.FREQUENCY_LIMIT.value:
            time.sleep(random.randint(5, 10))
        return data["data"] if get_data else data

    @retry(tries=10, delay=1)
    def _put(self, path, get_data=False, **data):
        data = {k: v for k, v in data.items() if v}
        response = self.session.put(
            path if path.startswith("http") else "https://open.feishu.cn/open-apis" + path,
            headers={"Authorization": f"Bearer {self.access_token}"},
            json=data,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code") == LarkError.FREQUENCY_LIMIT.value:
            time.sleep(random.randint(5, 10))
        return data["data"] if get_data else data

    def fetch_access_token(self):
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/"
        response = self.session.post(url, json={"app_id": self.app_id, "app_secret": self.secret})
        data = response.json()
        self.redis.setex(self.access_token_key, data["expire"], data["tenant_access_token"])
        return data["tenant_access_token"]

    def refresh_groups(self):
        groups = self.get_chats()["groups"]
        self.redis.setex(self.groups_key, 86400, json.dumps({g["chat_id"]: g["name"] for g in groups}))

    @property
    def access_token(self):
        token = self.redis.get(self.access_token_key)
        if not token:
            return self.fetch_access_token()
        return token.decode()

    @property
    def access_token_key(self):
        return f"feishu:{self.app_id}:access_token"

    @property
    def groups(self) -> Dict[str, str]:
        return json.loads(self.redis.get(self.groups_key) or "{}")

    @property
    def groups_key(self):
        return f"feishu:{self.app_id}:groups"


class LarkDocument(Lark):
    revision = 0

    def __init__(self, token):
        super().__init__()
        self.t = token

    def create_docs(self, title, folder_token="fldcnvQ8CYbYHpSlKuqIUaL5CEb", blocks: list = []):
        """ 创建文档 https://open.feishu.cn/document/ukTMukTMukTM/ugDM2YjL4AjN24COwYjN """
        return self._post(
            "/doc/v2/create",
            FolderToken=folder_token,
            Content=json.dumps(
                {"title": {"elements": [{"type": "textRun", "textRun": {"text": title}}]}, "body": {"blocks": blocks}}
            ),
            get_data=True,
        )

    def get_docs(self):
        """ 获取文档富文本内容 https://open.feishu.cn/document/ukTMukTMukTM/uUDM2YjL1AjN24SNwYjN """
        return self._get(f"/doc/v2/{self.t}/content", get_data=True)

    def update_docs(self, body: dict = {}):
        """ 编辑文档内容 https://open.feishu.cn/document/ukTMukTMukTM/uYDM2YjL2AjN24iNwYjN#e864198d """
        self.revision = self.revision or self.get_docs()["revision"]
        resp = self._post(
            f"/doc/v2/{self.t}/batch_update", Revision=self.revision, Requests=[json.dumps(body)], get_data=True
        )
        self.revision = resp.get("newRevision") or self.get_docs()["revision"]
        return resp

    def permission_transfer(self, member_id, type="doc", member_type="userid", token=None):
        """ 转移拥有者 https://open.feishu.cn/document/ukTMukTMukTM/uQzNzUjL0czM14CN3MTN """
        return self._post(
            "/drive/permission/member/transfer",
            token=token or self.t,
            type=type,
            owner={"member_type": member_type, "member_id": member_id},
            get_data=True,
        )

    """
    飞书文档新建和编辑时的数据结构
    https://open.feishu.cn/document/ukTMukTMukTM/ugDM2YjL4AjN24COwYjN
    https://open.feishu.cn/document/ukTMukTMukTM/uYDM2YjL2AjN24iNwYjN
    """

    @staticmethod
    def paragraph_data(text: str, style: dict = {}, text_style: dict = {}) -> dict:
        return {
            "type": "paragraph",
            "paragraph": {
                "elements": [{"type": "textRun", "textRun": {"text": text, "style": text_style}}],
                "style": style,
            },
        }

    @staticmethod
    def table_data(row_size: int, col_size: int, table_rows: list = [], table_style: dict = {}) -> dict:
        return {
            "type": "table",
            "table": {"rowSize": row_size, "columnSize": col_size, "tableRows": table_rows, "tableStyle": table_style},
        }

    @staticmethod
    def location_data(zone_id: str = "", index: int = 0, start_zone=False, end_zone=False) -> dict:
        return {"zoneId": zone_id, "index": index, "startOfZone": start_zone, "endOfZone": end_zone}

    @staticmethod
    def merge_table_cell_data(
        table_id: str, row_start: int = 0, row_end: int = 0, col_start: int = 0, col_end: int = 0
    ) -> dict:
        return {
            "requestType": "MergeTableCellsRequestType",
            "mergeTableCellsRequest": {
                "tableId": table_id,
                "rowStartIndex": row_start,
                "rowEndIndex": row_end,
                "columnStartIndex": col_start,
                "columnEndIndex": col_end,
            },
        }

    @staticmethod
    def insert_table_row_data(table_id: str, row_index: int) -> dict:
        return {
            "requestType": "InsertTableRowRequestType",
            "insertTableRowRequest": {"tableId": table_id, "rowIndex": row_index},
        }

    @staticmethod
    def insert_table_col_data(table_id: str, col_index: int) -> dict:
        return {
            "requestType": "InsertTableColumnRequestType",
            "insertTableColumnRequest": {"tableId": table_id, "columnIndex": col_index},
        }

    @staticmethod
    def insert_blocks_data(blocks: list, location: location_data) -> dict:
        return {
            "requestType": "InsertBlocksRequestType",
            "insertBlocksRequest": {"payload": json.dumps({"blocks": blocks}), "location": location},
        }


class LarkSheet(Lark):
    def __init__(self, token):
        super().__init__()
        self.t = token

    def create_sheet(self, title, folder_token=None):
        """ 创建文档 https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/sheets-v3/spreadsheet/create """
        resp = self._post("/sheets/v3/spreadsheets", title=title, folder_token=folder_token, get_data=True)
        self.t = resp.get("spreadsheet", {}).get("spreadsheet_token", "")
        return resp.get("spreadsheet") if resp.get("spreadsheet") else resp

    def get_sheet_info(self):
        """ 获取表格元数据 https://open.feishu.cn/document/ukTMukTMukTM/uETMzUjLxEzM14SMxMTN """
        return self._get(f"/sheets/v2/spreadsheets/{self.t}/metainfo", get_data=True)

    def add_sheet_dimension(self, body: dict):
        """ 增加行列 https://open.feishu.cn/document/ukTMukTMukTM/uUjMzUjL1IzM14SNyMTN """
        return self._post(f"/sheets/v2/spreadsheets/{self.t}/dimension_range", dimension=body, get_data=True)

    def write_cell_values(self, range_values: list):
        """ 向多个范围写入数据 https://open.feishu.cn/document/ukTMukTMukTM/uEjMzUjLxIzM14SMyMTN """
        return self._post(
            f"/sheets/v2/spreadsheets/{self.t}/values_batch_update", valueRanges=range_values, get_data=True
        )

    def update_cell_styles(self, data: list):
        """ 批量设置单元格样式 https://open.feishu.cn/document/ukTMukTMukTM/uAzMzUjLwMzM14CMzMTN """
        return self._put(f"/sheets/v2/spreadsheets/{self.t}/styles_batch_update", data=data, get_data=True)

    def merge_cells(self, ranges: str, types: str = "MERGE_ALL"):
        """ 合并单元格 https://open.feishu.cn/document/ukTMukTMukTM/ukDNzUjL5QzM14SO0MTN """
        return self._post(f"/sheets/v2/spreadsheets/{self.t}/merge_cells", range=ranges, mergeType=types, get_data=True)

    @staticmethod
    def sheet_data(row_size: int, col_size: int) -> dict:
        return {"type": "sheet", "sheet": {"rowSize": row_size, "columnSize": col_size}}

    @staticmethod
    def range_data(sheet_id: str, start_row: int, start_col: int, end_row: (int, str), end_col: int) -> str:
        return f"{sheet_id}!{chr(64 + start_col)}{start_row}:{chr(64 + end_col)}{end_row}"

    @staticmethod
    def insert_cell_styles(ranges: list, bold: bool = False, fore_color: str = None, italic: bool = False) -> dict:
        return {
            "ranges": ranges,
            "style": {
                "font": {"bold": bold, "italic": italic, "fontSize": "11pt/1.5"},
                "foreColor": fore_color,
                "hAlign": 0,
            },
        }

    @staticmethod
    def insert_cell_value(range_value: str, values: list) -> dict:
        return {"range": range_value, "values": values}


lark = Lark()
subscribe_approval()


class SupportType(hutils.TupleEnum):
    MESSAGE = "message", "文本消息推送"
    INTERACTIVE = "interactive", "卡片消息推送"
    APPROVAL_TASK = "approval_task", "审批任务流程推送"
    APPROVAL_INSTANCE = "approval_instance", "审批实例创建推送"
    ADD_BOT = "add_bot", "群聊天添加机器人"
    REMOVE_BOT = "remove_bot", "群聊天移除机器人"
    USER_ADD = "user_add", "员工入职"
    USER_UPDATE = "user_update", "员工信息更新"
    USER_STATUS_CHANGE = "user_status_change", "员工状态变更"


@require_http_methods(["POST"])
def handle(request: http.HttpRequest):
    data = lark.handle_data(json.loads(request.body))
    api.info(f"飞书推送：{data}")
    if data.pop("type", "") == "url_verification":
        return http.JsonResponse({"challenge": data.pop("challenge", "")})
    lark_event = data.get("event", {})
    if lark_event.get("type") not in SupportType.values():
        # TODO 目前只处理文本&审批流消息
        trace.info(f"处理异常：目前只处理文本&审批流消息;{data}")
        return http.JsonResponse({"message": "ok"})
    if lark_event.get("type") == SupportType.MESSAGE.value:
        message = lark_event.get("text_without_at_bot", lark_event.get("text", "")).strip()
        event = CommandEvent(
            user_id=lark_event.get("user_id"),
            open_id=lark_event.get("open_id"),
            chat_id=lark_event.get("open_chat_id"),
            endpoint=Endpoints.LARK.value,
            token=data.get("token"),
        )
        if message.startswith("/"):
            try:
                command_name, *text = message[1:].split(None, 1)
                text = text[0] if text else ""
                event.command_name = command_name
                event.text = text
            except:
                trace.warning(f"目前还不能处理这个message:{message}")
    elif lark_event.get("type") == SupportType.INTERACTIVE.value:
        event = CommandEvent(
            open_id=lark_event.get("open_id"),
            chat_id=lark_event.get("open_chat_id"),
            endpoint=Endpoints.LARK.value,
            card=lark_event.get("card", {}),
            command_name="echo",
            token=data.get("token"),
        )
    elif lark_event.get("type") in (SupportType.APPROVAL_TASK.value, SupportType.APPROVAL_INSTANCE.value):
        event = LarkApprovalEvent(
            open_id=lark_event.get("open_id"),
            endpoint=Endpoints.LARK.value,
            command_name=lark_event.get("type"),
            approval_code=lark_event.get("approval_code"),
            instance_code=lark_event.get("instance_code"),
        )
    elif lark_event.get("type") in (SupportType.ADD_BOT.value, SupportType.REMOVE_BOT.value):
        event = CommandEvent(
            chat_id=lark_event.get("open_chat_id"), endpoint=Endpoints.LARK.value, command_name="chats"
        )
    elif lark_event.get("type") in (
        SupportType.USER_ADD.value,
        SupportType.USER_UPDATE.value,
        SupportType.USER_STATUS_CHANGE.value,
    ):
        event = LarkApprovalEvent(
            open_id=lark_event.get("open_id"), endpoint=Endpoints.LARK.value, command_name=lark_event.get("type")
        )
    else:
        event = BaseEvent()
    try:
        event = Endpoints.LARK.handle_event(event)
        api.info(f"event：{event}")
    except BaseException as e:
        trace.error(str(e))
        event.error(str(e))
    return reply(event)


def reply(event):
    event = event if event else BaseEvent()
    if event.reply_type == ReplyTypes.TEXT:
        if event.user_ids is None and event.open_ids is None:
            lark.send_text(event.open_id, event.user_id, event.chat_id, event.reply_message)
        else:
            lark.batch_send_text(event.open_ids, event.user_ids, event.reply_message)
    elif event.reply_type == ReplyTypes.CARD:
        if event.user_ids is None and event.open_ids is None:
            lark.send_card(event.open_id, event.user_id, event.chat_id, event.reply_message)
        else:
            lark.batch_send_card(event.open_ids, event.user_ids, event.reply_message)
    elif event.reply_type == ReplyTypes.IMAGE:
        image_key = lark.upload_image(event.reply_message)
        if event.user_ids is None and event.open_ids is None:
            lark.send_image(event.open_id, event.user_id, event.chat_id, image_key)
        else:
            lark.batch_send_image(event.open_ids, event.user_ids, event.reply_message)
    elif event.reply_type == ReplyTypes.ERROR:
        if event.user_ids is None and event.open_ids is None:
            lark.send_text(event.open_id, event.user_id, event.chat_id, event.reply_message)
        else:
            lark.batch_send_text(event.open_ids, event.user_ids, event.reply_message)
    return http.JsonResponse({"message": event.reply_message}, status=event.http_status)


class LarkCard:
    class TagEnum(hutils.TupleEnum):
        PLAIN_TEXT = "plain_text"
        LARK_MD = "lark_md"

    class LayoutEnum(hutils.TupleEnum):
        BISECTED = "bisected"
        TRISECTION = "trisection"
        FLOW = "flow"

    class ButtonType(hutils.TupleEnum):
        DEFAULT = "default"
        PRIMARY = "primary"
        DANGER = "danger"

    @staticmethod
    def config(wide_screen_mode: bool = True, enable_forward: bool = True) -> dict:
        return {"wide_screen_mode": wide_screen_mode, "enable_forward": enable_forward}

    @staticmethod
    def header(content: str, color: str = None) -> dict:
        return {"title": {"tag": "plain_text", "content": content}, "template": color}

    @staticmethod
    def field(content: str, is_short: bool = False, tag=TagEnum.LARK_MD.value) -> dict:
        return {"is_short": is_short, "text": {"tag": tag, "content": content}}

    @staticmethod
    def content(content: str, tag: TagEnum = TagEnum.LARK_MD.value, fields: List[dict] = None) -> dict:
        """
        content是卡片内容，如果tag是md格式时，content支持md语法
        """
        return {"tag": "div", "text": {"tag": tag, "content": content}, "fields": fields}

    @staticmethod
    def divider() -> dict:
        return {"tag": "hr"}

    @staticmethod
    def button(content: str, url: str, button_type: ButtonType = ButtonType.DEFAULT.value, value: dict = None) -> dict:
        return {
            "tag": "button",
            "text": {"tag": "lark_md", "content": content},
            "multi_url": {"url": url},
            "type": button_type,
            "value": value,
        }

    @staticmethod
    def action(actions: List[dict], layout: LayoutEnum = LayoutEnum.BISECTED.value) -> dict:
        return {"tag": "action", "actions": actions, "layout": layout}

    @staticmethod
    def at(people: Union[str, List] = "all") -> str:
        people = [people] if isinstance(people, str) else people
        return "".join([f"<at id={i}></at>" for i in people])

    @staticmethod
    def card(header: header, elements: List, config: config = None) -> dict:
        """ https://open.feishu.cn/document/ukTMukTMukTM/ugTNwUjL4UDM14CO1ATN """
        return {"config": config or LarkCard.config(), "header": header, "elements": elements}

    @staticmethod
    def approval_detail_button(instance_code) -> dict:
        """ https://open.feishu.cn/document/uAjLw4CM/uYjL24iN/applink-protocol/supported-protocol/open-a-gadget """
        return LarkCard.button(
            content="查看详情",
            url=f"https://applink.feishu.cn/client/mini_program/open?appId=cli_9cb844403dbb9108&mode=sidebar-semi&path=pages%2Fdetail%2Findex%3FinstanceId%3D{instance_code}",
        )
