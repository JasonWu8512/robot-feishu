import dataclasses
import json
import logging
import re
from datetime import datetime
from typing import Dict, Iterator, List, Union
from urllib.error import URLError

import arrow
import funcy as fc
import hutils
import requests
from django.conf import settings
from hutils import list_first
from pandas import read_csv, read_excel, to_datetime
from retry import retry

from kevin.core import Bot
from kevin.endpoints import lark
from kevin.endpoints.management.commands.approval_enum import (
    ApprovalEnum,
    ApprovalStatusEnum,
    CheckOption,
    CoursesMethod,
    CoursesReason,
    CoursesType,
    LessonsLevel,
    PromoterUserType,
)
from kevin.endpoints.management.models import Account, AccountGuaId, LarkCallback
from kevin.events import LarkApprovalEvent, ReplyTypes

api = logging.getLogger("api")


@Bot.command(Bot("approval_task"))
def handle(event: LarkApprovalEvent):
    # 判断是否是支持的审批流类型
    if event.approval_code not in ApprovalEnum.values():
        # 不支持的审批流类型，记录日志并返回事件本身
        api.info(f"不支持的审批流类型：{event.approval_code}")
        return event

    # 先看有没有已经收到推送消息
    if LarkCallback.objects.filter(
            instance_code=event.instance_code,
            callback_type=event.command_name,
            status=ApprovalStatusEnum.APPROVED.value,
    ).exists():
        # 已经收到相同类型的已通过推送消息，记录日志并返回事件本身
        api.info("已收到相同类型的已通过推送消息")
        return event

    courses = ProcessApproval()  # 创建 ProcessApproval 对象，用于处理审批事件

    # 获取审批实例的详细数据和用户账户信息
    data = lark.lark.get_instance_detail(instance_code=event.instance_code)
    account = Account.objects.get(lark_user_id=data["user_id"])

    # 从审批实例数据中获取相应字段的值，并赋给 ProcessApproval 对象的属性
    courses.name, courses.status, form, start_time, event.user_id, event.open_id = hutils.get_data(
        data, "approval_name", "status", "form", "start_time", "user_id", "open_id"
    )

    courses.start_time = to_datetime(datetime.fromtimestamp(start_time / 1000)).strftime("%Y-%m-%d %H:%M:%S")

    # 将相关数据赋给 ProcessApproval 对象的属性，用于后续处理和日志记录
    courses.event, courses.account, courses.detail, courses.form = event, account, data, json.loads(form)

    # 记录审批相关的日志信息
    api.info(f"\n【审批】{courses.name}\n时间: {courses.start_time}\n提交: {account.name}({account.email})\n内容: {form}")

    ## 推送落库
    # 更新或创建 LarkCallback 对象，记录推送消息的相关信息
    LarkCallback.objects.update_or_create(
        instance_code=event.instance_code,
        callback_type=event.command_name,
        defaults={
            "approval_code": event.approval_code,
            "approval_name": courses.name,
            "status": courses.status,
            "user_id": data["user_id"],
            "user_name": account.name,
            "form": form,
        },
    )

    if courses.status != ApprovalStatusEnum.APPROVED.value:
        # 审批状态不是已通过，记录日志并返回事件本身
        api.info(f"【审批】任务{event.instance_code}状态为：{courses.status}")
        return event

    # 根据审批流类型处理相应的任务
    if event.approval_code == ApprovalEnum.FreePictureBookLesson.value:
        return courses.free_picture_book_lesson()
    elif event.approval_code == ApprovalEnum.NiuWaBackendAuth.value:
        return courses.niu_wa_backend_auth()
    elif event.approval_code in (ApprovalEnum.MentionDeveloped.value, ApprovalEnum.MentionDirectorDeveloped.value):
        return courses.packaging_test()
    elif event.approval_code in (ApprovalEnum.FreeActiveCourses.value, ApprovalEnum.FreeActiveCoursesTest.value):
        return courses.free_active_courses()
    elif event.approval_code == ApprovalEnum.CoursesSubLesson.value:
        return courses.sub_lesson_unlock()
    elif event.approval_code == ApprovalEnum.CreatePromoterAccount.value:
        return courses.create_promoter_account()
    elif event.approval_code == ApprovalEnum.RefundCourses.value:
        return courses.refund_courses_apply()

    # 默认情况下，返回事件本身
    return event


class ActiveCourses:
    @retry(tries=10, delay=1)
    def _get(self, path, get_data=False, **data):
        """
        发送 GET 请求并获取响应数据

        Args:
            path (str): 请求路径
            get_data (bool): 是否只获取响应数据的 "data" 字段，默认为 False
            **data: GET 请求的查询参数

        Returns:
            dict: 响应数据（如果 get_data=True，则为响应数据的 "data" 字段）

        Raises:
            requests.HTTPError: 如果请求返回错误状态码
        """
        response = requests.get(path, params=data)
        response.raise_for_status()  # 抛出异常如果返回错误状态码
        data = response.json()  # 解析响应数据为 JSON 格式
        if get_data:
            data = data["data"]
        return data

    @retry(tries=10, delay=1)
    def _post(self, path, **data):
        """
        发送 POST 请求并获取响应数据

        Args:
            path (str): 请求路径
            **data: POST 请求的 JSON 数据

        Returns:
            dict: 响应数据

        Raises:
            requests.HTTPError: 如果请求返回错误状态码
        """
        response = requests.post(path, json=data)
        return response.json()  # 解析响应数据为 JSON 格式

    def active_courses(
            self, user_list, level_list, buy_only=False, sub_lesson_unlock=False, check_option=None, start_time=None
    ):
        """
        激活课程

        Args:
            user_list (list): 用户列表
            level_list (list): 等级列表
            buy_only (bool): 是否仅购买，默认为 False
            sub_lesson_unlock (bool): 是否解锁子课程，默认为 False
            check_option: 检查选项
            start_time: 开始时间

        Returns:
            dict: 响应数据
        """
        return self._post(
            f"{settings.HOST}/inner/tools/purchase/v1",
            userList=user_list,
            levelList=level_list,
            source="feishu",
            buyOnly=buy_only,
            subLessonUnlock=sub_lesson_unlock,
            checkOption=check_option,
            startTime=start_time,
        )

    def refund_courses(self, user_list, level_list):
        """
        退款课程

        Args:
            user_list (list): 用户列表
            level_list (list): 等级列表

        Returns:
            dict: 响应数据
        """
        return self._post(
            f"{settings.HOST}/inner/tools/refund/v1", userList=user_list, levelList=level_list, source="feishu"
        )

    def active_ggr(self, ids):
        """
        激活 GGR 课程

        Args:
            ids: ID 列表

        Returns:
            dict: 响应数据
        """
        return self._post(
            f"{settings.GGR_HOST}/inner/customerrights/circulars/sendvip", id=[ids], duration="365", typ="guaid"
        )

    def active_picture_book(self, ids: list, courses: list, admin_user):
        """
        激活绘本课程

        Args:
            ids (list): ID 列表
            courses (list): 课程列表
            admin_user: 管理员用户

        Returns:
            dict: 响应数据
        """
        return self._post(
            f"{settings.HOST}/inner/tools/course/purchase/v1",
            guaids=ids,
            courses=courses,
            source="feishu",
            adminUser=admin_user,
        )

    def active_niu_wa_backend(self, env, email):
        """
        激活牛娃后台权限

        Args:
            env (str): 环境（"dev"、"fat" 或其他）
            email (str): 邮箱地址

        Returns:
            dict: 响应数据
        """
        if env == "dev":
            host = f"https://dev.jiliguala.com"
        elif env == "fat":
            host = f"https://fat.jiliguala.com"
        else:
            host = f"https://rc.jiliguala.com"
        return self._get(f"{host}/api/inner/niuwa/admin/permission?email={email}")

    def batch_import_promoter(self, ids: List[Dict]):
        """
        批量导入推广员信息

        Args:
            ids (list): 推广员信息列表

        Returns:
            dict: 响应数据
        """
        return self._post(f"{settings.PROMOTER_HOST}/api/promoter/batchImport", promoterInfos=ids)


@dataclasses.dataclass
class ProcessApproval(ActiveCourses):
    name: str = ""  # 审批名称
    status: ApprovalStatusEnum = ""  # 审批状态
    start_time: str = ""  # 审批开始时间
    event: LarkApprovalEvent = None  # 审批事件
    account: Account = None  # 账户信息
    lessons: str = ""  # 课程信息
    form: dict = dataclasses.field(default_factory=dict)  # 表单数据
    detail: dict = dataclasses.field(default_factory=dict)  # 详细数据
    lessons_level = {_.value: _.chinese for _ in LessonsLevel}  # 课程级别映射表
    promoter_type = {_.value: _.name for _ in PromoterUserType}  # 推广员类型映射表
    check_option = {_.value: _.chinese for _ in CheckOption}  # 检查选项映射表

    @staticmethod
    def active_courses_user_list(gua_ids, mobiles):
        """
        生成活跃课程的用户列表
        :param gua_ids: GuaID列表
        :param mobiles: 手机号列表
        :return: 用户列表
        """
        return [{"guaid": gua_id, "mobile": mobile} for gua_id, mobile in zip(gua_ids, mobiles)]

    @retry(tries=10, delay=1, exceptions=URLError)
    def get_csv_values(self, cols: Union[List, Iterator]):
        """
        从CSV或Excel文件中获取指定列的值
        :param cols: 列索引列表
        :return: 值列表
        """
        try:
            _, file_type = re.findall(r'"(http.+?)(csv|xlsx|xls)"', json.dumps(self.form))[0]
            url = "".join([_, file_type])
        except IndexError:
            raise ValueError("未匹配到csv/xlsx/xls文件")
        if file_type == "csv":
            try:
                values = read_csv(
                    url, dtype=str, skipinitialspace=True, na_filter=False, encoding_errors="ignore", usecols=cols
                ).values
            except ValueError as e:
                raise ValueError("文件解析失败，请检查文件内容或申请审批是否正确") from e
        else:
            values = read_excel(url, dtype=str, na_filter=False, usecols=cols).values
        if len(values[0]) == len(cols):
            return values
        else:
            raise ValueError("文件解析失败，请检查文件内容或申请审批是否正确")

    def get_level_list(self, name):
        """
        获取级别列表
        :param name: 小部件名称
        :return: 级别列表
        """
        lessons = self.widget_value(name)
        lessons = [lessons] if isinstance(lessons, str) else lessons
        self.lessons = "，".join(lessons)
        return list(fc.flatten([self.lessons_level[lesson.split("（")[0]] for lesson in lessons]))

    def widget_value(self, name):
        """
        获取小部件的值
        :param name: 小部件名称
        :return: 小部件的值
        """
        return list_first([widget["value"] for widget in self.form if name in widget["name"]])

    def free_active_courses(self):
        def multi_active_courses():
            try:
                cols = list(range(2))
                values = self.get_csv_values(cols=cols)
                # values = self.get_csv_values(cols=range(2))
            except ValueError as e:
                return self.event.error(message=e)
            gua_ids = []
            mobiles = []
            for gua_id, mobile in values:
                if gua_id is not None and mobile is not None:
                    gua_ids.append(gua_id.strip())
                    mobiles.append(mobile.strip())

            msg = f"你于{self.start_time}的申请「{self.name}-{self.lessons}」"

            sheet = lark.LarkSheet(None)
            docs = lark.LarkDocument(None)
            # 先创建一个文件，写入初始数据
            file = sheet.create_sheet("飞书申请开课名单")
            docs.permission_transfer(self.event.user_id, type="sheet", token=file["spreadsheet_token"])
            # 先回复一个文档链接（单用户开通消息），会修改回复类型，导致return时再发一次
            reply_msg = f"{msg}\n任务ID: {self.event.instance_code}\n{file['url']}"
            lark.reply(self.event.reply_text(message=reply_msg))
            self.event.reply_type = ReplyTypes.NO_REPLY

            sheet_id = sheet.get_sheet_info()["sheets"][0]["sheetId"]
            title = ["呱号", "手机号", "备注"]
            ranges = sheet.range_data(sheet_id, 1, 1, 1, len(title))
            sheet.write_cell_values(range_values=[sheet.insert_cell_value(range_value=ranges, values=[title])])

            start_row = 2
            user_list = self.active_courses_user_list(gua_ids=gua_ids, mobiles=mobiles)
            for user in fc.chunks(10, user_list):
                resp = self.active_courses(
                    user_list=user,
                    level_list=level_list,
                    check_option=check_option,
                    start_time=start_time,
                    buy_only=buy_only,
                )
                result = resp.get("data", {}).get("result", {})
                values = [
                    [
                        i["guaid"],
                        i["mobile"],
                        resp.get("msg", str(resp)) if result == {} else ",".join(result.get(i["guaid"])) or "OK",
                    ]
                    for i in user
                ]
                ranges = sheet.range_data(sheet_id, start_row, 1, start_row + len(user), len(title))
                sheet.write_cell_values(range_values=[sheet.insert_cell_value(range_value=ranges, values=values)])
                start_row += 10
            return reply_msg, file["url"]

        gua_id = self.widget_value("呱号填写")
        mobile = self.widget_value("手机号")
        level_list = self.get_level_list("开通课程选择")
        reason = self.widget_value("开课原因")
        # 开课审批流改版前的兼容方案
        courses_type = self.widget_value("开通方式") or CoursesType.SINGLE.value
        msg = f"你呱号{gua_id}于{self.start_time}的申请「{self.name}-{self.lessons}」"

        courses_msg = ggr_msg = None
        reply_msg, reply_all = None, False
        # 呱呱阅读是单独的接口，只有单独开课才能开
        if LessonsLevel.GGYD.name in level_list:
            if courses_type == CoursesType.SINGLE.value:
                ggr_msg = self.active_ggr(ids=gua_id).get("msgContent", "success")
            else:
                ggr_msg = "呱呱阅读只能单独开通"
            # 阅读课开完后开课列表删除呱呱阅读开课代码
            level_list.remove(LessonsLevel.GGYD.name)
        # 开课列表还有普通课
        if level_list:
            # 开课原因是2.5送3.0和推手项目，需要选择校验方式
            start_time = None
            check_option = None
            buy_only = False
            if reason in (CoursesReason.TO30.value, CoursesReason.PROMOTER.value):
                reply_all = True
                check_option = [self.check_option[option] for option in self.widget_value("校验方式")]
                if reason == CoursesReason.TO30.value:
                    # 选择了2.5送3.0，再选择开课方式
                    method = self.widget_value("开课方式")
                    # 选择了全开，需要传一年前的周一，其他不传
                    if method == CoursesMethod.ALL.value:
                        start_time = int(arrow.now().shift(weekday=0, years=-1, weeks=-1).timestamp())
                    else:
                        buy_only = True

            # 开通方式
            if courses_type == CoursesType.SINGLE.value:
                user_list = self.active_courses_user_list(gua_ids=gua_id.split(","), mobiles=mobile.split(","))
                resp = self.active_courses(
                    user_list=user_list,
                    level_list=level_list,
                    buy_only=buy_only,
                    check_option=check_option,
                    start_time=start_time,
                )
                result = resp.get("data", {}).get("result", {})
                courses_msg = resp.get("msg", str(resp)) if result == {} else ",".join(result.get(gua_id)) or "success"
            else:
                # 批量开通回复信息
                reply_msg, file_url = multi_active_courses()
                courses_msg = file_url

        LarkCallback.objects.filter(instance_code=self.event.instance_code).update(
            status=ApprovalStatusEnum.APPROVED.value, result=courses_msg, ggr_result=ggr_msg
        )
        # 是福利项目就只回复给发起人，其他发送给所有人
        # 组装单用户开通回复信息
        if courses_type == CoursesType.SINGLE.value:
            if courses_msg in ("success", None) and ggr_msg in ("success", None):
                # 通过后更新任务状态
                AccountGuaId.objects.get_or_create(account_id=self.account.id, gua_id=gua_id)
                reply_msg = f"恭喜！\n{msg}已经开通了！\n任务ID: {self.event.instance_code}"
            elif courses_msg in ("success", None):
                reply_msg = f"遗憾！\n{msg}申请失败了！\n任务ID: {self.event.instance_code}\n原因: 「呱呱阅读」{ggr_msg}"
            elif ggr_msg in ("success", None):
                reply_msg = f"遗憾！\n{msg}申请失败了！\n任务ID: {self.event.instance_code}\n原因: 「开课」{courses_msg}"
            else:
                reply_msg = f"遗憾！\n{msg}申请失败了！\n任务ID: {self.event.instance_code}\n原因: 「呱呱阅读」{ggr_msg}；「开课」{courses_msg}"

        if reply_all:
            # 因为批量开通已经提前回复了一条，所以不用再回复给申请人
            if courses_type == CoursesType.MULTI.value:
                # 审批流的所有人，除了发起者
                all_user = fc.flatten([i.get("user_id") or i.get("user_id_list") for i in self.detail["timeline"]])
                self.event.user_ids = list(set(fc.remove(self.event.user_id, all_user)))
            return self.event.reply_text(message=reply_msg)
        else:
            if courses_type == CoursesType.SINGLE.value:
                return self.event.reply_text(message=reply_msg)
            return self.event

    def free_picture_book_lesson(self):
        try:
            cols = list(range(2))
            values = self.get_csv_values(cols=cols)
            # values = self.get_csv_values(cols=range(2))
        except ValueError as e:
            return self.event.error(message=e)
        gua_ids = []
        lessons = []
        for gua_id, lesson in values:
            gua_ids.append(gua_id.strip()) if gua_id else None
            lessons.append(lesson.strip()) if lesson else None

        msg = f"你呱号{gua_ids}于{self.start_time}的申请「{self.name}-{lessons}」"

        resp = self.active_picture_book(ids=gua_ids, courses=lessons, admin_user=self.account.email)
        courses_msg = "success" if resp.get("code") == 0 else resp.get("msg", str(resp))
        # 通过后更新任务状态
        LarkCallback.objects.filter(instance_code=self.event.instance_code).update(
            status=ApprovalStatusEnum.APPROVED.value, picture_book_result=courses_msg
        )
        if courses_msg == "success":
            reply_msg = f"恭喜！\n{msg}已经开通了！\n任务ID: {self.event.instance_code}"
        else:
            reply_msg = f"遗憾！\n{msg}申请失败了！\n任务ID: {self.event.instance_code}\n原因: {courses_msg}"
        return self.event.reply_text(message=reply_msg)

    def niu_wa_backend_auth(self):
        env = self.widget_value("环境")
        resp = self.active_niu_wa_backend(env=env, email=self.account.email)
        courses_msg = "success" if resp.get("code") == 0 else resp.get("msg", str(resp))
        courses_data = resp.get("data") if resp.get("code") == 0 else {}

        LarkCallback.objects.filter(instance_code=self.event.instance_code).update(
            status=ApprovalStatusEnum.APPROVED.value, niuwa_be_result=courses_msg
        )

        if courses_msg == "success":
            if courses_data.get("type") == "new":
                reply_msg = f"恭喜！\n您的NiuWa Admin账号已经开通。请使用如下账号信息登录\n账号：{self.account.email}，密码：{courses_data.get('password')}\n任务ID: {self.event.instance_code}"
            else:
                reply_msg = f"恭喜！\n已为您开通NiuWa Admin权限。请使用绑定邮箱{self.account.email}账号登录\n任务ID: {self.event.instance_code}"
        else:
            reply_msg = (
                f"遗憾！\n{self.account.email}账号NiuWa Admin权限申请失败了！\n任务ID: {self.event.instance_code}\n原因: {courses_msg}"
            )
        return self.event.reply_text(message=reply_msg)

    def packaging_test(self):
        title = self.widget_value("提测需求")
        comment = hutils.list_first([i.get("comment") for i in self.detail.get("timeline") if "comment" in i]) or "无"
        if self.status == ApprovalStatusEnum.APPROVED.value:
            return self.event.reply_text(
                message=f"恭喜！\n您提交的「{self.name}-{title}」申请已通过！\n任务ID: {self.event.instance_code}\n通过意见: {comment}"
            )
        elif self.status == ApprovalStatusEnum.REJECTED.value:
            return self.event.reply_text(
                message=f"遗憾！\n您提交的「{self.name}-{title}」申请被驳回！\n任务ID: {self.event.instance_code}\n驳回意见: {comment}"
            )
        else:
            return self.event

    def sub_lesson_unlock(self):
        gua_id = self.widget_value("呱号填写")
        mobile = self.widget_value("手机号")
        level_list = self.get_level_list("需要解锁sublesson的级别")
        msg = f"你呱号{gua_id}于{self.start_time}的申请「{self.name}-{self.lessons}」"

        user_list = self.active_courses_user_list(gua_ids=gua_id.split(","), mobiles=mobile.split(","))
        resp = self.active_courses(user_list=user_list, level_list=level_list, sub_lesson_unlock=True)
        result = resp.get("data", {}).get("result", {})
        courses_msg = resp.get("msg", str(resp)) if result == {} else ",".join(result.get(gua_id)) or "success"

        # 通过后更新任务状态
        LarkCallback.objects.filter(instance_code=self.event.instance_code).update(
            status=ApprovalStatusEnum.APPROVED.value, sublesson_result=courses_msg
        )

        if courses_msg == "success":
            AccountGuaId.objects.get_or_create(account_id=self.account.id, gua_id=gua_id)
            return self.event.reply_text(message=f"恭喜！\n{msg}已经开通了！\n任务ID: {self.event.instance_code}")
        else:
            return self.event.reply_text(
                message=f"遗憾！\n{msg}申请失败了！\n任务ID: {self.event.instance_code}\n原因: {courses_msg}"
            )

    def create_promoter_account(self):
        try:
            cols = list(range(4))
            values = self.get_csv_values(cols=cols)
            # values = self.get_csv_values(cols=range(4))
        except ValueError as e:
            return self.event.error(message=e)
        promoter_infos = [
            {"guaid": gua_id, "mobile": mobile, "inviter": inviter, "identity": self.promoter_type[user_type].lower()}
            for mobile, gua_id, inviter, user_type in values
            # 有效数据才处理
            if mobile and gua_id
        ]

        msg = f"你于{self.start_time}的申请「{self.name}」"

        resp = self.batch_import_promoter(ids=promoter_infos)
        courses_msg = "success" if resp.get("code") == 0 else resp.get("msg", str(resp))
        courses_data = resp.get("data", []) if resp.get("code") == -1 else []

        # 通过后更新任务状态
        LarkCallback.objects.filter(instance_code=self.event.instance_code).update(
            status=ApprovalStatusEnum.APPROVED.value, promoter_result=courses_msg
        )
        if courses_msg == "success":
            return self.event.reply_text(message=f"恭喜！\n{msg}已经开通了！\n任务ID: {self.event.instance_code}")
        else:
            # 产品要求，每个消息限定账号数量：20 https://jiliguala.feishu.cn/docs/doccnPHfeyHGJpZO2o8P2TqZ3Dg#
            once_msg = f"遗憾！\n{msg}申请失败了！\n任务ID: {self.event.instance_code}\n原因:{courses_msg}\n"
            if courses_data:
                for reply_msg in fc.chunks(20, courses_data):
                    reply_msg = "\n".join(reply_msg)
                    lark.reply(self.event.reply_text(message=f"{once_msg}{reply_msg}"))
                    once_msg = ""
            else:
                return self.event.reply_text(message=f"{once_msg}")

    def refund_courses_apply(self):
        gua_id = self.widget_value("回收的呱号")
        mobile = self.widget_value("手机号")
        level_list = self.get_level_list("课程选择")
        user_list = self.active_courses_user_list(gua_ids=[gua_id], mobiles=[mobile])
        msg = f"你呱号{gua_id}于{self.start_time}的申请「{self.name}-{self.lessons}」"

        resp = self.refund_courses(user_list=user_list, level_list=level_list)
        courses_msg = "success" if resp.get("code") == 0 else resp.get("msg", str(resp))

        # 从这个审批流开始，结果都写在result里，不新加字段
        LarkCallback.objects.filter(instance_code=self.event.instance_code).update(
            status=ApprovalStatusEnum.APPROVED.value, result=courses_msg
        )
        if courses_msg == "success":
            # 通过后更新任务状态
            AccountGuaId.objects.filter(account_id=self.account.id, gua_id=gua_id).delete()
            reply_msg = f"恭喜！\n{msg}已经成功回收了！\n任务ID: {self.event.instance_code}"
        else:
            reply_msg = f"遗憾！\n{msg}申请失败了！\n任务ID: {self.event.instance_code}\n原因: {courses_msg}"
        return self.event.reply_text(message=reply_msg)


if __name__ == "__main__":
    event = LarkApprovalEvent()  # 创建 LarkApprovalEvent 类的实例
    handle(event)  # 调用 handle 函数并传递实例作为参数
