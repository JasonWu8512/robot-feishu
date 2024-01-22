import datetime
import re

import dateparser
import funcy as fc
import hutils
import jira
import requests
from django.conf import settings

from kevin.celery import app

JIRA = jira.JIRA(
    server=settings.JIRA_URL, auth=settings.JIRA_AUTH, get_server_info=False, options={"agile_rest_path": "agile"}
)
SPRINT_PATTERN = re.compile(r"id=(\d+),.*state=ACTIVE,name=(.*),startDate=(.*)T.*,endDate=(.*)T")


def get_all_sprints() -> dict:
    boards = JIRA.boards(type="scrum")
    board_sprints = [JIRA.sprints(b.id, state="active,future") for b in boards]
    sprints = {sprint.id: sprint for sprints in board_sprints for sprint in sprints}
    return sprints


def get_project_sprints(project) -> dict:
    boards = requests.get(
        f"{settings.JIRA_URL}rest/agile/1.0/board?projectKeyOrId={JIRA.project(project).id}", auth=settings.JIRA_AUTH
    ).json()["values"]
    board_sprints = sum([JIRA.sprints(board["id"], state="active,future") for board in boards], [])
    sprints = {sprint.id: sprint for sprint in board_sprints}
    return sprints


class Statuses(hutils.TupleEnum):
    IN_PROGRESS = "In Progress", "处理中"
    RESOLVED = "完成", "已关闭"
    FIXED = "Fixed", "完成"

    @property
    def nickname(self):
        return self.get_value_at(1)


class Agile:
    @classmethod
    def get_ticket_description(cls, issue_key):
        issue = JIRA.issue(issue_key)  # type: jira.Issue
        data, epic_description = issue.fields, ""
        if hasattr(data, "customfield_10100") and data.customfield_10100:
            epic = JIRA.issue(data.customfield_10100)
            if hasattr(epic.fields, "customfield_10102"):
                epic_description = f"史诗: {epic.fields.customfield_10102}"
        bug_owner = ""
        if (
            hasattr(data, "customfield_10108")
            and data.customfield_10108
            and data.customfield_10108.name != fc.silent(lambda: data.assignee.name)()
        ):
            bug_owner = f" (owner: {data.customfield_10108.displayName})"
        commit_type = "fix" if data.issuetype.name == "故障" else "feat"
        return "\n".join(
            [
                f"[{data.issuetype}] {issue.permalink()}",
                f"{issue_key}({commit_type}): {data.summary}",
                f"状态: {data.status.name}\n分锅: {data.reporter.displayName} -> {fc.silent(lambda: data.assignee.displayName)()}{bug_owner}",
                epic_description,
            ]
        ).strip()

    def __init__(self, project_key="QA"):
        self.project_key = project_key
        self.jira = JIRA

    def get_project_component(self) -> JIRA.component:
        return hutils.list_first(JIRA.project(self.project_key).components)

    def get_project_sprint(self) -> JIRA.sprint:
        sprints = get_project_sprints(self.project_key)
        return hutils.list_first(sprints.values())

    def add_issues_to_sprint(self, *issues):
        issue_keys = [
            i.key for i in issues if i.key.startswith(self.project_key + "-") and not i.fields.customfield_10100
        ]
        sprint = self.get_project_sprint()
        if sprint:
            self.jira.add_issues_to_sprint(sprint.id, issue_keys)

    def transition_issues(self, *issue_keys, to_status: Statuses):
        for issue_key in issue_keys:
            with hutils.mutes():
                transitions = self.jira.transitions(issue_key)
                for transition in transitions:
                    if transition["to"]["name"] in (to_status.value, to_status.nickname):
                        self.jira.transition_issue(issue_key, transition["id"])
                        break

    @app.task()
    def release_and_bind(self, version_name, issue_keys, description=""):
        date = str(datetime.date.today())
        with hutils.mutes():
            self.jira.create_version(
                name=version_name,
                project=self.project_key,
                description=description,
                releaseDate=date,
                startDate=date,
                released=True,
                archived=True,
            )
        for issue_key in issue_keys:
            issue = self.jira.issue(issue_key)
            issue.update(fixVersions=[{"set": [{"name": version_name}]}])
        self.transition_issues(*issue_keys, to_status=Statuses.RESOLVED)

    def load_work_report(self, start_date: datetime.date):
        jql = f'worklogDate >= "{start_date}"'
        issues = self.jira.search_issues(jql)
        for issue in issues:  # type: jira.Issue
            parent_key, parent_summary = "", ""
            if hasattr(issue.fields, "parent"):
                parent_key, parent_summary = issue.fields.parent.key, issue.fields.parent.fields.summary
            for work_log in self.jira.worklogs(issue.key):  # type: jira.Worklog
                started = self.parse_jira_datetime(work_log.started)
                Worklog.objects.get_or_create(
                    project_key=issue.fields.project.key,
                    issue_key=issue.key,
                    worklog_id=work_log.id,
                    defaults=dict(
                        username=work_log.author.name,
                        name=work_log.author.displayName,
                        issue_summary=issue.fields.summary,
                        parent_key=parent_key,
                        parent_summary=parent_summary,
                        started_at=started,
                        started_date=started.date(),
                        comment=work_log.comment[: Const.LEN.DESCRIPTION],
                        seconds_spent=min(work_log.timeSpentSeconds, 3600 * 8 * 5),
                    ),
                )

    def parse_jira_datetime(self, time_string) -> datetime.datetime:
        return dateparser.parse(time_string).replace(tzinfo=None) + datetime.timedelta(hours=8)
