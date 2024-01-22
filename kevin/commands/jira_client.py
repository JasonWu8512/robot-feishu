from typing import Optional

import funcy as fc
import hutils
import jira

from kevin.core import Kevin
from kevin.endpoints.agile import Agile
from kevin.endpoints.management.commands import guess_username
from kevin.endpoints.management.models import Account, Patterns
from kevin.events import CommandEvent


class JiraTeam(hutils.TupleEnum):
    QA = "QA", "QA"
    NB = "NB", "麒麟"
    MBE = "MBE", "运营"
    INF = "INF", "基建"
    YM = "YM", "医美"
    FE = "FE", "前端"


class JiraManager:
    def process(self):
        data = {}
        issue_data = {"fields": data}

        if self.issue:
            issue = self.jira.issue(self.issue)
            if self.sentry_issue:
                if self.sentry_issue.jira_issue_key and self.sentry_issue.jira_issue_key != issue.key:
                    self.sentry_issue.unlink()
                if not self.sentry_issue.jira_issue_key:
                    self.sentry_issue.link(issue.key)
            if self.namespace.type and issue.fields.issuetype.name not in {self.issuetype, "Wish"}:
                data["issuetype"] = {"name": self.issuetype}
            if self.namespace.reporter and issue.fields.reporter.name != self.reporter:
                data["reporter"] = {"name": self.reporter}

        elif self.sentry_issue:
            issue_key = self.sentry_issue.jira_issue_key or self.sentry_issue.create(
                self.project,
                self.summary,
                self.assignee,
                self.bug_owner,
            )
            issue = self.jira.issue(issue_key)

        else:
            data.update(
                {
                    "project": self.project,
                    "issuetype": {"name": self.issuetype},
                    "summary": self.summary,
                    "reporter": {"name": self.reporter},
                    "assignee": {"name": self.assignee},
                    "description": self.description,
                    "components": [{"name": self.component}],
                }
            )
            if self.issuetype == "Bug":
                data["customfield_10108"] = {"name": self.bug_owner}
                data["customfield_10111"] = {"value": "Unknown"}
                data["customfield_10110"] = {"value": "Unknown"}
            if self.issuetype == "Task":
                data["fixVersions"] = [{"name": hutils.list_first(self.jira.project(self.project).versions).name}]
                data["timetracking"] = {"originalEstimate": self.time, "remainingEstimate": self.time}
            self.update_epic_data(data)
            issue = self.jira.create_issue(**issue_data)
            if self.current_sprint:
                self.agile.add_issues_to_sprint(issue)
            return issue

        if self.summary and issue.fields.summary != self.summary:
            data["summary"] = self.summary
        if self.namespace.assignee and issue.fields.assignee.name != self.assignee:
            data["assignee"] = {"name": self.assignee}
        if issue.fields.issuetype == "Bug" and not issue.fields.customfield_10108:
            data["customfield_10108"] = {"name": self.bug_owner}

        if self.namespace.epic or (self.epic and not issue.fields.customfield_10100):
            self.update_epic_data(data)

        if data:
            issue.update(**issue_data)

        if self.current_sprint:
            self.agile.add_issues_to_sprint(issue)

        return issue

    def update_epic_data(self, data):
        if Patterns.JIRA_ISSUE.match(self.epic):
            epic = self.jira.issue(self.epic)
            assert epic.fields.issuetype == "Epic"
        else:
            epic_jql = (
                f"project = {self.project} AND issuetype = Epic AND "
                f'"Epic Status" != Done AND "Epic Name" ~ {self.epic}'
            )
            epic = hutils.list_first(self.jira.search_issues(epic_jql))
        if epic:
            data.update(customfield_10100=epic.key)

    def __init__(self, event: CommandEvent):
        self.event = event
        self.namespace = event.options
        event.username = Account.objects.get(lark_open_id=event.open_id).name
        self.account = event.account
        self.account.name = event.account_name
        self.project = self.account.default_jira_project  # type: str
        if self.namespace.project:
            self.project = self.namespace.project
            if self.account.default_jira_project != self.project:
                self.account.modify(default_jira_project=self.project)
        self.project = self.project.upper()
        self.assignee = guess_username(self.namespace.assignee or self.account.name)  # type: str
        self.reporter = guess_username(self.namespace.reporter or self.account.name)  # type: str
        self.bug_owner = guess_username(self.namespace.owner) if self.namespace.owner else self.assignee
        self.current_sprint = self.namespace.current_sprint
        self.time = self.namespace.time  # str
        self.issuetype = self.namespace.type or "Task"  # type: str
        self.agile = Agile(self.project)
        self.jira = self.agile.jira

        self.component = fc.silent(lambda: self.agile.get_project_component().name)()

        self.issue = self.namespace.issue  # type: str
        if self.issue and hutils.is_int(self.issue):
            self.issue = f"{self.project}-{self.issue}"

        self.sentry_issue = None  # type: Optional[SentryIssue]
        if self.namespace.summary and Patterns.SENTRY_ISSUE.search(self.namespace.summary):
            self.namespace.sentry = self.namespace.summary
            self.namespace.summary = ""
        if self.namespace.sentry:
            match = Patterns.SENTRY_ISSUE.search(self.namespace.sentry)
            assert match
            domain, issue_id = match.groups()
            self.sentry_issue = SentryIssue(issue_id=issue_id, domain=domain)

        self.epic = self.namespace.epic
        if self.sentry_issue or self.issuetype == "Bug":
            self.epic = self.epic or "缺陷修复"
        if self.issuetype == "Wish":
            self.epic = self.epic or "许愿池"
        self.epic = self.epic or "各类杂活"

        self.summary = self.namespace.summary  # type: str
        if self.summary and len(" ".join([self.summary, *self.namespace.descriptions])) < 50:
            self.summary = " ".join([self.summary, *self.namespace.descriptions])
            self.description = f"{event.username}({self.account.pinyin})"
        else:
            self.description = "\n".join([f"{event.username}({self.account.pinyin})", *self.namespace.descriptions])
        assert self.issue or self.sentry_issue or self.summary
        if self.issuetype == "Wish":
            if self.summary and not self.summary.startswith("【许愿】"):
                self.summary = "【许愿】" + self.summary
            if not self.namespace.assignee:
                self.assignee = "bot"


@Kevin.command(
    Kevin("jira", intro="一键创建 Jira Ticket")
    .arg("--issue", "-i", default=None)
    .arg("--sentry", "-s", default="")
    .arg("--project", "-p", default="")
    .arg("--assignee", "-a", default="")
    .arg("--reporter", "-r", default="")
    .arg("--epic", "-e", default="")
    .arg("--owner", "-o", default="")
    .arg("--current-sprint", "-cs", action="store_true")
    .arg("--type", "-t", default=None, choices=["Bug", "Story", "Task"])
    .arg("--time", default="2m")
    .arg("summary", nargs="?")
    .arg("descriptions", nargs="*")
)
def create_jira_ticket(event: CommandEvent):
    namespace = event.options
    if namespace.type == "Bug" and not namespace.issue:
        return event.reply_text("DEPRECATED:\n`/jira -t Bug` is deprecated, use `/bug` instead.")
    manager = JiraManager(event)
    try:
        issue = manager.process()
    except jira.JIRAError as ex:
        return event.error(ex)
    return event.reply_text(Agile.get_ticket_description(issue.key))


@Kevin.command(
    Kevin("bug", intro="一键创建 Jira Bug")
    .arg("--issue", "-i", default=None)
    .arg("--sentry", "-s", default="")
    .arg("--project", "-p", default="")
    .arg("--assignee", "-a", default="")
    .arg("--reporter", "-r", default="")
    .arg("--epic", "-e", default="")
    .arg("--owner", "-o", default="")
    .arg("--current-sprint", "-cs", action="store_true")
    .arg("--type", "-t", default="Bug", choices=["Bug"])
    .arg("--time", default=None)
    .arg("summary", nargs="?")
    .arg("descriptions", nargs="*")
)
def create_jira_bug(event: CommandEvent):
    manager = JiraManager(event)
    issue = manager.process()
    return event.reply_text(Agile.get_ticket_description(issue.key))


@Kevin.command(Kevin("vote", intro="支持一个事情").arg("something"))
def vote_something(event: CommandEvent):
    account = event.account
    return event.reply_text(f"{account.name}给{event.options.something}投出了关键的一票支持")
