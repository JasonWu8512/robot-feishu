import datetime
import re
import uuid

import hutils
import pypinyin
from django.core.exceptions import ValidationError
from django.db import models as db

from kevin.zero.models import AuthUser


class Const:
    """ 常量+限制 (Constants + Constraints) """

    class BARE:
        """ 默认的空值 """

        DATETIME = datetime.datetime.utcfromtimestamp(0)
        INT = -1
        JSON = "{}"
        STR = ""

    class LEN:
        """ 默认的长度 """

        APPID = 20
        DESCRIPTION = 255
        JSON = 1023
        NAME = 50
        OPENID = 30
        PHONE = 11
        URL = 255
        TEXT = 10000

    class Val:
        @classmethod
        def check_regex(cls, string):
            for regex in string.split():
                try:
                    re.search(regex, "")
                except Exception as ex:
                    raise ValidationError(str(ex))


class Patterns:
    COMMIT_TAGS = re.compile(r"\(([\w/]+)\)")
    COMMIT_PREFIX = re.compile(r"^([\w/]+)[:(]")
    CONFLUENCE_PAGE = re.compile(r".*http[s]?://udon-inter.*pageId=(\d+).*")
    GITLAB_MR_URL = re.compile(r".*\bpasta.zaihui.com.cn/(.*)/-/merge_requests/([\d]+)\b.*")
    HTML_TITLE = re.compile(r"<title[^>]*>([^<]+?)</title>")
    JIRA_ISSUE = re.compile(r"([A-Z]{2,11}-\d{2,7})")
    SENTRY_ISSUE = re.compile(r".*/(sentry.kezaihui.com|sentry-test.zaihuiba.com)/.*/issues/(\d+)/.*")
    URL = re.compile(r"(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)")
    WHO = re.compile(r"(.* |^)(.{1,6})和(.{1,6})[谁哪].*")


class DeactivatedManager(db.Manager):
    def get_queryset(self):
        return super(DeactivatedManager, self).get_queryset().filter(deactivated_at=Const.BARE.DATETIME)


class BaseModel(db.Model, hutils.ModelMixin):
    class Meta:
        abstract = True

    uid = db.UUIDField(default=uuid.uuid4, editable=False, unique=True, help_text="全宇宙唯一身份")
    created_at = db.DateTimeField(auto_now_add=True, editable=False, help_text="创建时间")
    updated_at = db.DateTimeField(auto_now=True, editable=False, help_text="上次修改时间")
    deactivated_at = db.DateTimeField(
        default=Const.BARE.DATETIME, db_index=True, editable=False, help_text="失效时间（1970年为未失效）"
    )

    objects = DeactivatedManager()  # 默认过滤掉 deactivated_at 的数据
    all_objects = db.Manager()  # 需要取的话，从 Model.all_objects.filter(...) 里面取

    def __str__(self):
        return str(self.pk)


class Account(BaseModel):
    name = db.CharField(max_length=Const.LEN.NAME, null=True, blank=True, verbose_name="姓名", help_text="姓名")
    phone = db.CharField(max_length=Const.LEN.PHONE, null=True, blank=True, verbose_name="手机号", help_text="手机号")
    email = db.CharField(max_length=Const.LEN.NAME, null=True, blank=True, verbose_name="邮箱", help_text="邮箱")
    english_name = db.CharField(max_length=Const.LEN.NAME, null=True, blank=True, verbose_name="英文", help_text="英文")

    # Jira 相关
    default_jira_project = db.CharField(
        max_length=Const.LEN.NAME, default="QA", verbose_name="默认 Jira 项目", help_text="默认 Jira 项目"
    )
    sync_calendar = db.BooleanField(default=False, verbose_name="开启 Jira 与企业微信的日程同步", help_text="开启 Jira 与企业微信的日程同步")
    # GitLab 相关
    default_gitlab_project = db.CharField(
        max_length=Const.LEN.NAME, null=True, verbose_name="默认 GitLab 项目", help_text="默认 GitLab 项目"
    )
    # 微信相关
    unionid = db.CharField(
        max_length=Const.LEN.OPENID, null=True, unique=True, editable=False, verbose_name="用户的 UnionID"
    )
    alarm_openid = db.CharField(
        max_length=Const.LEN.OPENID,
        null=True,
        unique=True,
        editable=False,
        verbose_name="报警公众号的 OpenID",
        help_text="报警公众号的 OpenID",
    )
    is_subscribe = db.BooleanField(default=False, editable=False, verbose_name="是否关注公众号", help_text="是否关注公众号")
    user_info = db.TextField(default="{}", editable=False, verbose_name="微信用户信息", help_text="微信用户信息")

    # 企业微信相关
    wxwork_user_id = db.CharField(
        max_length=Const.LEN.OPENID, default="", editable=False, verbose_name="企业微信 UserId", help_text="企业微信 UserId"
    )

    # 飞书相关
    lark_open_id = db.CharField(
        max_length=Const.LEN.NAME, null=True, editable=False, verbose_name="飞书 ID", help_text="飞书 ID"
    )
    lark_user_id = db.CharField(
        max_length=Const.LEN.NAME, null=True, editable=False, verbose_name="飞书 USER_ID", help_text="飞书 USER_ID"
    )

    # 点餐相关
    enable_vesta = db.BooleanField(default=False, verbose_name="开启美餐点餐", help_text="开启美餐点餐")
    password_jira = db.CharField(default="", null=True, max_length=256, help_text="jira密码")
    user_role = db.CharField(null=True, max_length=Const.LEN.NAME, help_text="用户类型")

    class Meta:
        db_table = "ace_account"
        verbose_name = verbose_name_plural = "账号信息"

    @property
    def pinyin(self):
        return "".join(pypinyin.lazy_pinyin(self.name))

    @property
    def jira_name(self):
        try:
            return AuthUser.objects.get(email=self.email).username
        except AuthUser.DoesNotExist:
            return

    @classmethod
    def who_named(cls, pinyin) -> "Account":
        return cls.objects.get(english_name=pinyin)


class AccountGuaId(BaseModel):
    account_id = db.CharField(
        max_length=Const.LEN.NAME, null=True, editable=False, verbose_name="用户ID", help_text="用户ID"
    )
    gua_id = db.CharField(max_length=Const.LEN.NAME, null=True, editable=False, verbose_name="呱ID", help_text="呱ID")

    class Meta:
        db_table = "ace_account_gua_id"


class LarkCallback(BaseModel):
    approval_code = db.CharField(
        max_length=Const.LEN.NAME, null=True, editable=False, verbose_name="任务code", help_text="任务code"
    )
    approval_name = db.CharField(
        max_length=Const.LEN.NAME, null=True, editable=False, verbose_name="任务名称", help_text="任务名称"
    )
    instance_code = db.CharField(
        max_length=Const.LEN.NAME, null=True, editable=False, verbose_name="实例code", help_text="实例code"
    )
    callback_type = db.CharField(
        max_length=Const.LEN.NAME, null=True, editable=False, verbose_name="飞书回调类型", help_text="飞书回调类型"
    )
    status = db.CharField(
        max_length=Const.LEN.NAME, null=True, editable=False, verbose_name="审批任务状态", help_text="审批任务状态"
    )
    form = db.CharField(max_length=Const.LEN.TEXT, null=True, verbose_name="审批表单详情", help_text="审批表单详情")
    user_id = db.CharField(max_length=Const.LEN.NAME, null=True, verbose_name="提交人", help_text="提交人")
    user_name = db.CharField(max_length=Const.LEN.NAME, null=True, verbose_name="提交人姓名", help_text="提交人姓名")
    result = db.CharField(max_length=Const.LEN.JSON, null=True, verbose_name="执行结果", help_text="执行结果")
    ggr_result = db.CharField(max_length=Const.LEN.JSON, null=True, verbose_name="执行结果", help_text="执行结果")
    picture_book_result = db.CharField(max_length=Const.LEN.JSON, null=True, verbose_name="绘本结果", help_text="绘本结果")
    niuwa_be_result = db.CharField(max_length=Const.LEN.JSON, null=True, verbose_name="牛娃后台", help_text="牛娃后台")
    sublesson_result = db.CharField(max_length=Const.LEN.JSON, null=True, verbose_name="子课程解锁", help_text="子课程解锁")
    promoter_result = db.CharField(max_length=Const.LEN.DESCRIPTION, null=True, help_text="推广人账户")

    class Meta:
        db_table = "ace_lark_callback"


class Department(BaseModel):
    name = db.CharField(max_length=Const.LEN.NAME, null=True, blank=True, verbose_name="部门名称", help_text="部门名称")
    department_id = db.CharField(
        max_length=Const.LEN.NAME, unique=True, null=True, blank=True, verbose_name="部门ID", help_text="部门ID"
    )
    open_department_id = db.CharField(
        max_length=Const.LEN.NAME, unique=True, null=True, blank=True, verbose_name="部门OPEN ID", help_text="部门OPEN ID"
    )
    parent_department_id = db.CharField(
        max_length=Const.LEN.NAME, null=True, blank=True, verbose_name="父部门ID", help_text="父部门ID"
    )
    parent_open_department_id = db.CharField(
        max_length=Const.LEN.NAME, null=True, blank=True, verbose_name="父部门OPEN ID", help_text="父部门OPEN ID"
    )
    parent_open_department_ids = db.CharField(
        max_length=Const.LEN.TEXT, null=True, blank=True, verbose_name="父部门OPEN IDS", help_text="父部门OPEN IDS"
    )
    leader_id = db.CharField(
        max_length=Const.LEN.NAME, null=True, blank=True, verbose_name="leader ID", help_text="leader ID"
    )
    leader_email = db.CharField(
        max_length=Const.LEN.NAME, null=True, blank=True, verbose_name="leader 邮箱", help_text="leader 邮箱"
    )
    count = db.CharField(max_length=Const.LEN.NAME, null=True, blank=True, verbose_name="部门人数", help_text="部门人数")

    class Meta:
        db_table = "ace_department"


class DepartmentAccount(BaseModel):
    open_department_id = db.CharField(max_length=Const.LEN.NAME, blank=True, verbose_name="部门 ID", help_text="部门 ID")
    account_id = db.CharField(max_length=Const.LEN.NAME, blank=True, verbose_name="用户ID", help_text="用户ID")
    is_active = db.BooleanField(max_length=Const.LEN.NAME, blank=True, null=True, verbose_name="是否在职")

    class Meta:
        db_table = "ace_department_account"


class Chat(BaseModel):
    chat_id = db.CharField(max_length=Const.LEN.NAME, blank=True, verbose_name="群聊ID", help_text="群聊ID")
    description = db.CharField(max_length=Const.LEN.DESCRIPTION, blank=True, verbose_name="群聊描述", help_text="群聊描述")
    name = db.CharField(max_length=Const.LEN.NAME, blank=True, verbose_name="群聊名称", help_text="群聊名称")
    owner_user_id = db.CharField(max_length=Const.LEN.NAME, blank=True, verbose_name="群主ID", help_text="群主ID")

    class Meta:
        db_table = "ace_chat"


class JiraProjectChat(BaseModel):
    project = db.CharField(max_length=Const.LEN.NAME, blank=True, verbose_name="jira项目")
    chat_id = db.CharField(max_length=Const.LEN.NAME, blank=True, null=True, verbose_name="群聊id")
    is_active = db.BooleanField(max_length=Const.LEN.NAME, blank=True, null=True, verbose_name="激活")

    class Meta:
        db_table = "ace_jira_project_chat"


class GitlabProjectChat(BaseModel):
    project = db.CharField(max_length=Const.LEN.NAME, blank=True, verbose_name="gitlab项目")
    chat_id = db.CharField(max_length=Const.LEN.NAME, blank=True, null=True, verbose_name="群聊id")
    source_branch = db.CharField(max_length=Const.LEN.NAME, blank=True, null=True, verbose_name="来源分支")
    target_branch = db.CharField(max_length=Const.LEN.NAME, blank=True, null=True, verbose_name="目标分支")
    is_active = db.BooleanField(max_length=Const.LEN.NAME, blank=True, null=True, verbose_name="激活")
    is_jira_active = db.BooleanField(max_length=Const.LEN.NAME, blank=True, null=True, verbose_name="gitlab与jira联动激活")

    class Meta:
        db_table = "ace_gitlab_project_chat"


class GitlabProject(BaseModel):
    project = db.CharField(max_length=Const.LEN.NAME, blank=True, verbose_name="gitlab项目", help_text="gitlab项目")
    path = db.CharField(max_length=Const.LEN.NAME, blank=True, verbose_name="项目路径", help_text="项目路径")
    project_id = db.CharField(max_length=Const.LEN.NAME, blank=True, verbose_name="项目id", help_text="项目id")
    project_namespace = db.CharField(max_length=Const.LEN.NAME, blank=True, verbose_name="项目空间", help_text="项目空间")

    class Meta:
        db_table = "ace_gitlab_project"


class StorySubTaskRelation(BaseModel):
    sub_task = db.CharField(max_length=Const.LEN.NAME, blank=True, null=True, help_text="子任务")
    story = db.CharField(max_length=Const.LEN.NAME, blank=True, null=True, help_text="故事")

    class Meta:
        db_table = "ace_story_subtask_relation"
