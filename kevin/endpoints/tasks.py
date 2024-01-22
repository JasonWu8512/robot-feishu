import datetime
import hashlib
import json
import logging
from collections import defaultdict

import arrow
import gitlab
import jira
import requests
from django.conf import settings
from gitlab.v4.objects import MergeRequest
from retry import retry

from kevin.celery import app
from kevin.core import Bot, Endpoints, Kevin
from kevin.endpoints import lark
from kevin.endpoints.agile import Agile, Statuses
from kevin.endpoints.code import CodeBase
from kevin.endpoints.management.commands.approval_enum import ApprovalEnum, ApprovalStatusEnum
from kevin.endpoints.management.models import (
    Account,
    Chat,
    GitlabProject,
    GitlabProjectChat,
    LarkCallback,
    Patterns,
    StorySubTaskRelation,
)
from kevin.events import CommandEvent, LarkApprovalEvent
from kevin.utils import Redis

logger = logging.getLogger(__name__)


@app.task()
def fetch_active_courses_status():
    """ 查询开课审批状态 """
    callback = LarkCallback.objects.filter(
        callback_type=lark.SupportType.APPROVAL_TASK.value,
        status__in=[ApprovalStatusEnum.PENDING.value, ApprovalStatusEnum.TRANSFERRED.value],
    ).exclude(approval_code__in=[ApprovalEnum.MentionDeveloped.value, ApprovalEnum.MentionDirectorDeveloped.value])
    for item in callback:
        event = LarkApprovalEvent(
            endpoint=Endpoints.LARK.value,
            command_name=lark.SupportType.APPROVAL_TASK.value,
            approval_code=item.approval_code,
            instance_code=item.instance_code,
        )
        try:
            event = Bot.COMMANDS[event.command_name](event)
            lark.reply(event)
        except BaseException as e:
            logging.info(f"【查询开课审批状态】开课失败了，{event}\n{e}")


@app.task()
def fetch_diamond_stock_alarm(room):
    def get_token():
        url = f"http://10.10.174.108/api/admin/auth/login"
        u, p = "gideon_bao@jiliguala.com", "19961230baoqikun"
        md5 = hashlib.md5()
        md5.update(p.encode("utf-8"))
        return requests.post(url=url, json={"u": u, "p": md5.hexdigest()}).json()["data"]["token"]

    def fields_data(index, item):
        return {
            "is_short": False,
            "text": {
                "tag": "lark_md",
                "content": f"{index}) {item['id']}、{item['name']}、{item['total'] - item['bought']}、{'是' if item['promoterZone'] else '否'}",
            },
        }

    items = requests.get(url="http://jiliguala.com/api/admin/diamond/items", headers={"admintoken": get_token()}).json()
    items = [item for item in items["data"]["diamondItems"] if item["status"] and item["total"] - item["bought"] <= 30]
    items.sort(key=lambda x: x["promoterZone"])  # 按照是否排序
    fields = [fields_data(index + 1, item) for index, item in enumerate(items)]
    card = {
        "config": {"wide_screen_mode": True, "enable_forward": True},
        "header": {"title": {"tag": "plain_text", "content": "每日库存报警"}, "template": "orange"},
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**序号、礼品id、礼品名称、礼品当前库存、是否为推广人专区礼品**",
                },
                "fields": fields,
            },
            {"tag": "div", "text": {"tag": "lark_md", "content": "<at id=all></at>"}},
        ],
    }
    event = CommandEvent(chat_id=room, endpoint=Endpoints.LARK.value, card=card, command_name="echo")
    event = Kevin.COMMANDS[event.command_name](event)
    lark.reply(event)


@app.task()
def polling_latest():
    client = CodeBase.get_gitlab()
    merge_requests = client.mergerequests.list(scope="all")
    redis = Redis.client()

    # 先获取最新的pr和上一次已经存在的pr
    latest_merge_requests = {
        f"{i.id}": {
            "state": i.state,
            "processed": False,
            "project_id": i.project_id,
            "iid": i.iid,
            "created_at": i.created_at[:10],
        }
        for i in merge_requests
    }
    exist_merge_requests = json.loads(redis.get("merge_requests") or json.dumps(latest_merge_requests))

    # 进行数据比对，有发现pr状态发生变更，把pr是否处理的flag置为FALSE
    for merged_request_id, value in latest_merge_requests.items():
        # 将最新pr的增量数据写入到已存在pr字典里
        exist_merge_requests[merged_request_id] = exist_merge_requests.get(merged_request_id, value)
        if value["state"] != exist_merge_requests[merged_request_id]["state"]:
            exist_merge_requests[merged_request_id]["state"] = value["state"]
            exist_merge_requests[merged_request_id]["processed"] = False

    merge_requests_map = {f"{i.id}": i for i in merge_requests}
    for i, value in exist_merge_requests.items():
        if not value["processed"]:
            merge_request = merge_requests_map.get(
                i, client.projects.get(value["project_id"]).mergerequests.get(value["iid"])
            )
            project = client.projects.get(merge_request.project_id)
            if GitlabProjectChat.objects.filter(project=project.path_with_namespace, is_jira_active=True):
                update_merge_request.apply_async((merge_request.project_id, merge_request.iid))
            if merge_request.author["username"] != "docker" and merge_request.state == "merged":
                hint_merged_request(project, merge_request)
            value["processed"] = True

    # 删除已存在pr字典里1个月前的记录
    exist_merge_requests = {
        k: v
        for k, v in exist_merge_requests.items()
        if (datetime.datetime.now() - datetime.datetime.strptime(v["created_at"], "%Y-%m-%d")).days < 30
    }
    redis.set("merge_requests", json.dumps(exist_merge_requests))


@app.task()
def update_merge_request(project_id, merge_request_iid, retries=0):
    if retries:
        return

    # 获取一堆参数
    project = CodeBase.get_gitlab().projects.get(project_id)
    try:
        merge_request = project.mergerequests.get(merge_request_iid)
        if merge_request.source_branch == "master":
            return
    except gitlab.GitlabError:
        return
    update_labels(merge_request)
    if "skip ace" in (merge_request.description or "").strip().lower():
        return

    username = merge_request.author["username"]
    if username in {"docker", "admin"}:
        return

    # 检查 Ticket 有效性
    issue_keys = list(set(Patterns.JIRA_ISSUE.findall(merge_request.title)))
    agile = Agile()
    issues = []
    if issue_keys:
        for issue_key in issue_keys:
            try:
                issue = agile.jira.issue(issue_key)
            except jira.JIRAError as ex:
                merge_request.discussions.create(data={"body": f"`{issue_key}` 在 Jira 上有报错：`{ex.text}`"})
                continue
            try:
                StorySubTaskRelation.objects.update_or_create(**{"sub_task": issue.id, "story": issue.fields.parent.id})
            except AttributeError:
                pass
            issues.append(issue)
            if issue.fields.issuetype.name == "Wish":
                merge_request.discussions.create(data={"body": f"`{issue.key}` 是许愿类型！请修正为正确类型！"})
            if "bugfix" not in merge_request.labels and issue.fields.issuetype.name == "Bug":
                merge_request.labels.append("bugfix")
                merge_request.save()
            if issue.fields.assignee.name != username:
                merge_request.discussions.create(
                    data={"body": f"`{issue.key}` 是 {issue.fields.assignee.name} 在做！请使用你自己的 Ticket!"}
                )
            if issue.fields.issuetype.name == "Epic":
                merge_request.discussions.create(
                    data={"body": f"友情提示：最好不要直接关联 Epic 类型 (`{issue.key}`), 请使用 Story 或者 Sub-Task"}
                )
    if not issues:
        protected_branches = {"dev", "freeze", "master"}
        is_same_project = merge_request.source_project_id == merge_request.target_project_id
        is_protected_merge = (
            is_same_project
            and merge_request.source_branch in protected_branches
            and merge_request.target_branch in protected_branches
        )
        if not retries and not is_protected_merge:
            merge_request.discussions.create(
                data={"body": "标题请以 Jira Issue Key 开头，比如 `QA-25(feat): do something`\n\n可以在描述中增加 `skip ace` 以跳过本检查"}
            )
        return
    # 调整状态
    agile.transition_issues(*issue_keys, to_status=Statuses.IN_PROGRESS)
    check_merge_request.apply_async((project_id, merge_request_iid), countdown=10)
    agile.add_issues_to_sprint(*issues)
    account = Account.objects.filter(english_name=username).first()  # type: Account
    if not account or not account.password_jira:
        return
    instance = jira.JIRA(server=settings.JIRA_URL, auth=(username, account.password_jira))
    time_spent = merge_request.time_stats()["total_time_spent"]
    comment = "自动记录日志"
    if time_spent:
        comment = merge_request.description
    else:
        time_spent = 1200  # by default 20m
    for issue_key in issue_keys:
        logger.info(f"logging jira work for {issue_key} of {username}")
        instance.add_worklog(
            issue=issue_key, timeSpentSeconds=time_spent, comment=f"{merge_request.web_url}\n{comment}".strip()
        )


def update_labels(merge_request: MergeRequest):
    # 判断要不要打上 migration/script 的标签
    changes = merge_request.changes()["changes"]
    has_migration = any([_["new_file"] and "migrations" in _["new_path"] for _ in changes])
    if has_migration and "migration" not in merge_request.labels:
        merge_request.labels.append("migration")
    has_script = any([_["new_file"] and "script" in _["new_path"] for _ in changes])
    if has_script and "script" not in merge_request.labels:
        merge_request.labels.append("script")
    match = Patterns.COMMIT_TAGS.search(merge_request.title) or Patterns.COMMIT_PREFIX.search(merge_request.title)
    if match:
        tags = [t.strip(", ").lower() for ts in match.group(1).split("/") for t in ts.split(",")]
        mapping = {
            "base": "base",
            "bug": "bugfix",
            "bugfix": "bugfix",
            "chore": "chore",
            "ci": "ci",
            "deploy": "deploy",
            "doc": "document",
            "document": "document",
            "feat": "feature",
            "feature": "feature",
            "fix": "bugfix",
            "hotfix": "bugfix",
            "inf": "infrastructure",
            "infra": "infrastructure",
            "llfan": "llfan",
            "llka": "llka",
            "llmgd": "llmgd",
            "lltuan": "lltuan",
            "mi": "migration",
            "migration": "migration",
            "perf": "performance",
            "performance": "performance",
            "refact": "refactor",
            "refactor": "refactor",
            "research": "research",
            "rev": "revert",
            "revert": "revert",
            "style": "style",
            "unittest": "unittest",
            "ut": "unittest",
        }
        for tag in tags:
            if tag in mapping and mapping[tag] not in merge_request.labels:
                merge_request.labels.append(mapping[tag])
    try:
        merge_request.save()
    except gitlab.GitlabUpdateError:
        logger.info(f"GitlabUpdateError: {merge_request.attributes}")


@app.task()
def check_merge_request(project_id, merge_request_iid, countdown=10):
    if Redis.client().exists(f"mr:{project_id}:{merge_request_iid}"):
        return
    project = CodeBase.get_gitlab().projects.get(project_id)
    try:
        merge_request = project.mergerequests.get(merge_request_iid)
    except gitlab.GitlabError:
        return
    if merge_request.state == "closed":
        return
    if merge_request.state != "merged":
        countdown = min(countdown + 10, 1800)
        Redis.client().set(f"mr:{project_id}:{merge_request_iid}", "1", ex=countdown - 10)
        check_merge_request.apply_async((project_id, merge_request_iid, countdown), countdown=countdown)
        return
    issue_keys = list(set(Patterns.JIRA_ISSUE.findall(merge_request.title)))
    Agile().transition_issues(*issue_keys, to_status=Statuses.FIXED)


def hint_merged_request(project, merge_request):
    elements = [
        {"tag": "div", "text": {"tag": "plain_text", "content": "标题："}},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"[{merge_request.title}]($urlVal)",
                "href": {"urlVal": {"url": merge_request.web_url}},
            },
        },
        {"tag": "div", "text": {"tag": "plain_text", "content": "方向："}},
        {
            "tag": "div",
            "text": {"tag": "plain_text", "content": f"{merge_request.source_branch} -> {merge_request.target_branch}"},
        },
    ]

    card = {
        "config": {"wide_screen_mode": True, "enable_forward": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"{project.path_with_namespace} 项目合并了 PR"},
            "template": "wathet",
        },
        "elements": elements,
    }

    description = (
        (merge_request.description or "")
        .replace("## 版本:\nFeature:\n  -", "")
        .replace("Bugfix:\n  -", "")
        .replace(" \n\n", "")
        .replace("\n  -\n", "")
        .replace("Others:\n  -", "")
        .replace("- [ ] 自己在手机上测过了吗\n", "")
        .replace("  - [ ] 安卓测过了\n", "")
        .replace("  - [ ] IOS测过了\n", "")
        .replace("- [ ] 如果涉及到重要模块，有告知相关人员吗", "")
        .strip()
    )
    if description == merge_request.title:
        description = ""
    if description:
        elements.append({"tag": "div", "text": {"tag": "plain_text", "content": "描述："}}),
        elements.append({"tag": "div", "text": {"tag": "plain_text", "content": description}}),

    elements.append({"tag": "div", "text": {"tag": "plain_text", "content": "作者："}}),
    author = merge_request.author["username"]
    try:
        user_id = Account.who_named(author).lark_open_id
    except Account.DoesNotExist:
        user_id = ""
    elements.append(
        {"tag": "div", "text": {"tag": "lark_md", "content": f"<at id={user_id}></at>" if user_id else author}}
    )

    for gitlab_project in GitlabProjectChat.objects.filter(project=project.path_with_namespace, is_active=True):
        # 没有source_branch配置就不校验
        if not gitlab_project.source_branch:
            gitlab_project.source_branch = merge_request.source_branch
        if (
            gitlab_project.target_branch in merge_request.target_branch
            and gitlab_project.source_branch in merge_request.source_branch
        ):
            event = CommandEvent(
                chat_id=Chat.objects.get(id=gitlab_project.chat_id).chat_id,
                endpoint=Endpoints.LARK.value,
                card=card,
                command_name="echo",
            )
            event = Kevin.COMMANDS[event.command_name](event)
            lark.reply(event)


@app.task()
def sync_gitlab_project():
    client = CodeBase.get_gitlab()
    for project in client.projects.list(all=True, as_list=True, visibility="private"):
        GitlabProject.objects.update_or_create(
            project=project.name,
            defaults={
                "path": project.path_with_namespace,
                "project_id": project.id,
                "project_namespace": project.namespace.get("full_path"),
            },
        )


@app.task()
def create_monthly_report(user_id, docs=None, date=None):
    @retry(tries=10, delay=1)
    def login_zero():
        return requests.post(
            "https://zero.jiliguala.com/v1/user/login", data={"username": "admin", "password": "wocao404"}
        ).json()["token"]

    @retry(tries=10, delay=1)
    def get_report():
        resp = requests.get(
            f"https://zero.jiliguala.com/v1/jira/month/report?month={date}", headers={"Authorization": token}
        ).json()["data"]
        # 给数据整形下
        for detail in resp["details"]:
            detail.update({"P0": 0, "P1": 0, "P2": 0, "P3": 0, "S0": 0, "S1": 0, "S2": 0, "S3": 0})
            for bug in detail["bugs"] or []:
                if bug["bug_level"] == "线上":
                    detail[bug["sub_bug_level"]] = bug["count"]
                elif bug["bug_level"] == "线下":
                    detail[bug["sub_bug_level"]] = bug["count"]
        return resp

    @retry(tries=10, delay=1)
    def get_department():
        resp = requests.get(
            f"https://zero.jiliguala.com/v1/jira/department/month/report?month={date}", headers={"Authorization": token}
        ).json()["data"]
        # 给数据整形下
        for detail in resp["details"]:
            try:
                detail["first_depart"], detail["second_depart"] = detail["depart_name"].split("/")
            except ValueError:
                detail["first_depart"] = detail["second_depart"] = detail["depart_name"].split("/")[0]
            detail.update({"P0": 0, "P1": 0, "P2": 0, "P3": 0, "S0": 0, "S1": 0, "S2": 0, "S3": 0})
            for bug in detail["bugs"] or []:
                if bug["bug_level"] == "线上":
                    detail[bug["sub_bug_level"]] = bug["count"]
                elif bug["bug_level"] == "线下":
                    detail[bug["sub_bug_level"]] = bug["count"]
        return resp

    def write_data(title, value, data, sheet_id):
        title_range = sheet.range_data(sheet_id, 1, 1, 1, len(title))
        # 标题数据
        title_data = sheet.insert_cell_value(range_value=title_range, values=[title])
        # 写数据
        value_range = sheet.range_data(sheet_id, 2, 1, len(data) + 1, len(title))
        values = [
            [
                "" if details[value[col_index]] is None else details[value[col_index]]
                for col_index, col in enumerate(title)
            ]
            for row_index, details in enumerate(data)
        ]
        value_data = sheet.insert_cell_value(range_value=value_range, values=values)
        sheet.write_cell_values(range_values=[title_data, value_data])
        # 默认格式
        all_range = sheet.range_data(sheet_id, 1, 1, len(data) + 1, len(title))
        # 第一列格式
        first_col_range = sheet.range_data(sheet_id, 1, 1, len(data) + 1, 1)
        sheet.update_cell_styles(
            data=[
                sheet.insert_cell_styles(ranges=[all_range]),
                sheet.insert_cell_styles(ranges=[title_range, first_col_range], bold=True),
            ]
        )

    def write_online_quality(sheet_id):
        write_data(online_title, online_value, jira_data["details"], sheet_id)
        # 线上bug数超过1加粗标红
        bugs_index = [
            [row_index + 2, col_index + 1]
            for col_index, col in enumerate(online_title)
            for row_index, details in enumerate(jira_data["details"])
            if 0 < col_index < (len(online_title) - 1) and details[online_value[col_index]] > 0
        ]
        sheet_styles = [
            sheet.insert_cell_styles(
                ranges=[sheet.range_data(sheet_id, row, col, row, col)], bold=True, fore_color=red_text_color
            )
            for row, col in bugs_index
        ]
        sheet.update_cell_styles(data=sheet_styles)

    def write_offline_quality(sheet_id):
        write_data(offline_title, offline_value, jira_data["details"], sheet_id)
        # 线下S0和线下bug指数加粗加红
        range_value = [sheet.range_data(sheet_id, 2, 2, "", 2), sheet.range_data(sheet_id, 2, 8, "", 8)]
        sheet_styles = sheet.insert_cell_styles(ranges=range_value, bold=True, fore_color=red_text_color)
        sheet.update_cell_styles(data=[sheet_styles])

    def write_depart_quality(sheet_id):
        write_data(depart_title, depart_value, depart_data["details"], sheet_id)
        # 先合并单元格
        depart_rows = defaultdict(list)
        for index, details in enumerate(depart_data["details"]):
            depart_rows[details["first_depart"]].append(index + 2)
        for _, index in depart_rows.items():
            if len(index) > 1:
                sheet.merge_cells(ranges=sheet.range_data(sheet_id, index[0], 1, index[-1], 1))
        # 第一列左对齐
        first_col_range = sheet.range_data(sheet_id, 1, 1, len(depart_data["details"]) + 1, 1)
        # 第二列加粗
        second_col_range = sheet.range_data(sheet_id, 1, 2, len(depart_data["details"]) + 1, 2)
        # 线下S0和线下bug指数加粗加红
        range_value = [sheet.range_data(sheet_id, 2, 3, "", 3), sheet.range_data(sheet_id, 2, 9, "", 9)]
        sheet.update_cell_styles(
            data=[
                sheet.insert_cell_styles(ranges=[first_col_range], bold=True),
                sheet.insert_cell_styles(ranges=[second_col_range], bold=True),
                sheet.insert_cell_styles(ranges=range_value, bold=True, fore_color=red_text_color),
            ]
        )

    # 创建初始文档
    now = arrow.now().shift(months=-1)
    date = date if date else now.strftime("%Y-%m")
    start_row = start_col = 1
    red_text_color = "#D83931"
    docs = docs if docs else create_doc(user_id, now, start_row, start_col)

    # 登录测试平台
    token = login_zero()
    jira_data = get_report()
    depart_data = get_department()

    # 开始插入新行数据
    doc_blocks = json.loads(lark.LarkDocument(docs["objToken"]).get_docs()["content"])["body"]["blocks"]
    sheet_blocks = [block["sheet"]["token"].split("_") for block in doc_blocks if block["type"] == "sheet"]
    sheet_token, sheet_ids = sheet_blocks[0][0], [sheet_block[1] for sheet_block in sheet_blocks]
    sheet = lark.LarkSheet(sheet_token)

    online_title = ["项目", "线上P0", "线上P1", "线上P2", "线上P3", "合计"]
    online_value = ["proj_name", "P0", "P1", "P2", "P3", "online_count"]

    offline_title = ["项目", "线下S0", "线下S1", "线下S2", "线下S3", "开发人数", "开发人天", "线下Bug指数", "线下Bug解决时间(小时)", "线下Bug关闭时长（小时）"]
    offline_value = [
        "proj_name",
        "S0",
        "S1",
        "S2",
        "S3",
        "people_count",
        "day",
        "offline_bug_rate",
        "avg_fix_time",
        "avg_close_time",
    ]
    depart_title = [
        "一级部门",
        "二级部门",
        "线下S0",
        "线下S1",
        "线下S2",
        "线下S3",
        "开发人数",
        "开发人天",
        "线下Bug指数",
        "线下Bug解决时间(小时)",
        "线下Bug关闭时长（小时）",
    ]
    depart_value = [
        "first_depart",
        "second_depart",
        "S0",
        "S1",
        "S2",
        "S3",
        "people_count",
        "day",
        "offline_bug_rate",
        "avg_fix_time",
        "avg_close_time",
    ]

    write_online_quality(sheet_ids[0])
    write_offline_quality(sheet_ids[1])
    write_depart_quality(sheet_ids[2])


def create_doc(user_id, now, start_row=1, start_col=1):
    # 创建初始文档
    date = now.strftime("%Y-%m")
    title = now.strftime("质量月报-%Y年%m月")
    doc = lark.LarkDocument(None)
    sheet = lark.LarkSheet
    block = [
        doc.paragraph_data(text="线上质量", style={"headingLevel": 2}),
        sheet.sheet_data(row_size=start_row, col_size=start_col),
        doc.paragraph_data(text="线下质量", style={"headingLevel": 2}),
        doc.paragraph_data(text="产品线", style={"list": {"type": "bullet", "indentLevel": 1}, "headingLevel": 3}),
        sheet.sheet_data(row_size=start_row, col_size=start_col),
        doc.paragraph_data(text="组织架构线", style={"list": {"type": "bullet", "indentLevel": 1}, "headingLevel": 3}),
        sheet.sheet_data(row_size=start_row, col_size=start_col),
        doc.paragraph_data(text="测试平台质量月报链接", style={"headingLevel": 2}),
        doc.paragraph_data(text=f"http://qa.jiliguala.com/#/monthReport?month={date}"),
        doc.paragraph_data(text="指标说明：", style={"headingLevel": 3}),
        doc.paragraph_data(text="Bug指数 = 线下bug分 / 总人天数"),
        doc.paragraph_data(text="线下bug分 = S0_count * 20 + S1_count * 5 + S2_count * 3 + S3_count * 1"),
        doc.paragraph_data(text="线上Bug解决时间 = Bug创建时间到Bug关闭时间之间的时长"),
        doc.paragraph_data(text="人均人天数 = 总人天/实际资源人数"),
    ]
    docs = doc.create_docs(title, "", block)
    print(docs)
    doc.permission_transfer(user_id, token=docs["objToken"])
    return docs
