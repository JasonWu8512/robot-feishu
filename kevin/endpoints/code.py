import datetime
import os
import re
import time

import git
import gitlab
import hutils
import requests
from django.conf import settings
from gitlab.v4.objects import MergeRequest, Project

from kevin.celery import app


class CommandError(Exception):
    """ 可预期的执行错误 """


class CodeBaseException(Exception):
    """ CodeBase 过程中出现的错误 """


class MergeSettings:
    def __init__(self, gitlab_settings, **fields):
        self.gitlab_settings = gitlab_settings
        self.fields = fields
        self.old_fields = {}

    def __enter__(self):
        for key, new_value in self.fields.items():
            old_value = getattr(self.gitlab_settings, key)
            if old_value != new_value:
                self.old_fields[key] = old_value
                setattr(self.gitlab_settings, key, new_value)
            if self.old_fields:
                self.gitlab_settings.save()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.old_fields:
            return
        for key, old_value in self.old_fields.items():
            setattr(self.gitlab_settings, key, old_value)
        self.gitlab_settings.save()


class CodeBase:

    DEFAULT_PUSH_ACCESS_LEVEL = 0  # NOTE 任何人都不能push -f

    @classmethod
    def get_jira_project_key(cls, project_name: str) -> str:
        if project_name.startswith("stdev"):
            return "ST"
        return {
            "BE/basic-services/bragi": "GE",
            "BE/basic-services/delphi": "NB",
            "BE/basic-services/hestia": "ZW",
            "BE/basic-services/rhea": "GE",
            "BE/basic-services/shennong": "NB",
            "BE/inf/hera": "NB",
            "BE/marketing/alita": "NB",
            "BE/marketing/angelia": "GE",
            "BE/marketing/crawler": "NB",
            "ME/magneto": "NB",
            "ME/spiderman": "ME",
            "fe/inf/spartan-cli": "FE",
            "fe/kylin": "NB",
            "fe/pc/business-pc": "GE",
            "win/huiorder": "WIN",
            "zaihui/deploy": "INF",
            "zaihui/hunger-game": "ST",
        }.get(project_name, "")

    def get_next_tag(self):
        tags = self.gitlab_project.tags.list(per_page=1)
        today = datetime.date.today()
        next_tag = f"v{today.year}.{today.month}.{today.day}"
        if not tags:  # first tag
            return next_tag
        tag = tags[0].name
        if tag == next_tag:  # same day, two versions
            return f"{next_tag}-1"
        if tag.startswith(next_tag):  # same day, three or more versions
            try:
                counter = int(tag.rsplit("-", 1)[-1])
                return f"{next_tag}-{counter + 1}"
            except ValueError:
                pass
        return next_tag

    @classmethod
    def get_gitlab(cls, token=settings.GITLAB_TOKEN) -> gitlab.Gitlab:
        return gitlab.Gitlab(settings.GITLAB_URL, token, api_version="4")

    def __init__(self, project="zaihui/server"):
        self.project = project.rsplit("/")[-1]
        projects = self.get_gitlab().projects.list(search=self.project, per_page=500, simple=True, archived=False)
        projects = [
            p
            for p in projects
            if any(p.path_with_namespace.startswith(ns + "/") for ns in ["be", "fe", "zaihui"])
            and (p.name == self.project or p.path_with_namespace == self.project)
        ]
        if not projects:
            raise CodeBaseException(f"没有在 GitLab 上找到 {self.project} 这个项目，是不是手误打错了？")
        if len(projects) > 1:
            raise CodeBaseException("找到多个匹配，请选择唯一匹配哦：\n" + "\n".join(p.path_with_namespace for p in projects))
        self.gitlab_project: Project = self.get_gitlab().projects.get(projects[0].id)
        self.project = projects[0].path_with_namespace
        self.remote = "origin"
        self.path = os.path.join("./deploy/data", "gitlab", self.project)
        repo_url = f"http://pasta.inter.zaihui.com.cn/{self.project}.git"
        if os.path.exists(self.path):
            self.git = git.Repo(self.path).git
            self.git.remote("set-url", "origin", repo_url)
            return
        parent_dir = os.path.dirname(self.path)
        if not os.path.exists(parent_dir):
            os.makedirs(os.path.dirname(self.path))
        self.git = git.Repo.clone_from(repo_url, self.path).git

    def update(self):
        self.git.fetch()
        self.git.remote("prune", "origin")
        self.git.config("user.email", "engineer@kezaihui.com")
        self.git.config("user.name", "engineer")
        return self

    def get_remote_branch(self, branch):
        return f"{self.remote}/{branch}"

    def merge(self, source, target):
        self.update()

        remote_source, remote_target = map(self.get_remote_branch, [source, target])
        branches = {b.strip() for b in self.git.branch("-r").split("\n") if b.strip().startswith(self.remote)}
        for branch in [remote_source, remote_target]:
            if branch not in branches:
                raise CodeBaseException("远端没有{}分支".format(branch))
        if not self.git.log(f"{remote_target}..{remote_source}"):
            raise CodeBaseException(f"{source} 与 {target} 分支目前不需要 merge 哦")
        self.git.reset("--hard", remote_target)
        try:
            self.git.merge("--no-ff", "--no-commit", remote_source)
        except git.GitCommandError as ex:
            lines = "\n".join([line.split(":", 1)[-1].strip() for line in str(ex).split("\n") if "CONFLICT" in line])
            raise CodeBaseException(f"{source}和{target}分支有冲突，请手动解决\n{lines}".strip())
        with hutils.mutes(git.GitCommandError):
            self.git.merge("--abort")

        project = self.gitlab_project
        with hutils.catches(
            raises=CodeBaseException(
                f"机器人在创建 Merge Request 时报错，请检查是否赋予 bot 项目权限：\n"
                f"{settings.GITLAB_URL}/{self.project}/-/project_members"
            )
        ):
            merge_request = self.create_merge_request(source, target, "合并 {} 到 {}".format(source, target))
        url = settings.GITLAB_MR_URL.format(project=self.project, pr_iid=merge_request.iid)

        # 查验是否需要 fast forward
        try:
            self.git.merge_base("--is-ancestor", remote_target, remote_source)
            merge_method = "ff"
        except git.GitCommandError:
            merge_method = "merge"
        with MergeSettings(project, merge_method=merge_method):
            self.force_merge(merge_request)
        time.sleep(1)
        return url

    def force_merge(self, merge_request):
        project_settings = MergeSettings(self.gitlab_project, only_allow_merge_if_pipeline_succeeds=False)
        approval_settings = MergeSettings(
            self.gitlab_project.approvals.get(),
            merge_requests_author_approval=True,
            disable_overriding_approvers_per_merge_request=False,
        )
        merge_request_settings = MergeSettings(merge_request.approvals.get(), approvals_required=0)
        with project_settings, approval_settings, merge_request_settings:
            merge_request.merge()

    def create_merge_request(self, source, target, title, description="") -> MergeRequest:
        project = self.gitlab_project
        try:
            return project.mergerequests.create(
                {
                    "source_branch": source,
                    "target_branch": target,
                    "title": title,
                    "description": description,
                    "squash": False,
                }
            )
        except gitlab.GitlabCreateError as ex:
            if str(ex.response_code) == "409":
                return project.mergerequests.get(re.search(r"!(\d+)", str(ex.error_message)).group(1))
            raise

    def hotfix(self, target, change_log=None, approve=False):
        """ 发了 hotfix 以后，补上一个 Tag """
        merge_requests = self.get_merge_requests(target, target)
        description = change_log or self.get_description(merge_requests)
        if not description:
            raise CodeBaseException("根据在下的判断，这次没什么好发的。\n真要发的话请手动。")
        return self.prepare_merge_request_and_tag(description, target, target, merge_requests[0], approve=approve)

    def release(self, source, target, change_log=None, approve=False):
        merge_requests = self.get_merge_requests(source, target)
        description = change_log or self.get_description(merge_requests)
        if not description:
            self.update()
            if self.git.diff(f"origin/{source}", f"origin/{target}"):
                description = "> 本次发版不含有 PR 内容"
        if not description:
            raise CodeBaseException("根据在下的判断，这次没什么好发的。\n真要发的话请手动。")
        return self.prepare_merge_request_and_tag(description, source, target, approve=approve)

    def prepare_merge_request_and_tag(self, description, source, target, merge_request=None, approve=False):
        release_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        tag = self.get_next_tag()
        title = f"【发版】{tag} 于 {release_time}点 ({source} to {target})"
        merge_request = merge_request or self.create_merge_request(source, target, title, description=description)
        url = settings.GITLAB_MR_URL.format(project=self.project, pr_iid=merge_request.iid)
        # issue_keys = list(set(Patterns.JIRA_ISSUE.findall(description)))
        # jira_project_key = self.get_jira_project_key(self.project)
        # if jira_project_key and issue_keys:
        #     agile = Agile(jira_project_key)
        #     version_name = f"{self.gitlab_project.name} - {tag}"
        #     agile.release_and_bind.delay(version_name=version_name, issue_keys=issue_keys, description=url)
        if approve:
            with hutils.mutes():
                self.force_merge(merge_request)
        create_new_tag.apply_async((self.project, merge_request.iid, tag, description), countdown=10)
        return tag, url

    def get_merge_requests(self, source, target, hotfix=False):
        project = self.gitlab_project
        if hotfix:
            last_commit = project.tags.list(per_page=1)[0].commit["created_at"]
        else:
            target_merge_requests = project.mergerequests.list(
                target_branch=target, state="merged", scope="created_by_me", per_page=1
            )
            if target_merge_requests:
                last_commit = target_merge_requests[0].created_at
            else:
                last_commit = (datetime.datetime.now() - datetime.timedelta(days=14)).isoformat()
        source_merge_requests = project.mergerequests.list(
            target_branch=source, state="merged", updated_after=last_commit, per_page=500
        )
        merge_requests = [
            mr
            for mr in source_merge_requests
            if mr.merged_at and mr.merged_at > last_commit and mr.author["username"] != "docker"
        ]
        return merge_requests

    def get_description(self, merge_requests):
        description = []
        for merge_request in merge_requests:
            author = merge_request.author["username"]
            description.append(f"- {merge_request.title} (!{merge_request.iid} @{author})")
        description = "\n".join(description)
        return description

    def approve(self, mr, token):
        url = "{}projects/{}/merge_requests/{}/approve".format(settings.GITLAB_API_URL, mr.project_id, mr.iid)
        requests.post(url, headers={"PRIVATE-TOKEN": token})

    def protect(self, branch_name, undo=False):
        if undo and branch_name in ("dev", "freeze", "master"):
            raise CommandError("dev/freeze/master 是我们约定的原始分支哦，不能乱玩")
        if undo:
            self.gitlab_project.protectedbranches.delete(branch_name)
        else:
            self.gitlab_project.protectedbranches.create(
                data={"push_access_level": self.DEFAULT_PUSH_ACCESS_LEVEL, "name": branch_name}
            )


@app.task()
def create_new_tag(project_name, merge_request_iid, tag_name, description):
    project = CodeBase(project_name).gitlab_project
    merge_request = project.mergerequests.get(merge_request_iid)
    if merge_request.state == "closed":
        return
    if merge_request.state != "merged":
        create_new_tag.apply_async((project_name, merge_request_iid, tag_name, description), countdown=10)
        return
    merge_request_url = settings.GITLAB_MR_URL.format(project=project_name, pr_iid=merge_request_iid)
    project.tags.create(
        data={
            "tag_name": tag_name,
            "ref": "master",
            "message": f"release {tag_name} at {merge_request_url}",
            "release_description": description,
        }
    )
