import json
import logging

import requests
from django import http

from kevin.endpoints import lark
from kevin.endpoints.management.models import Account
from kevin.events import LarkApprovalEvent

cmdb_url = "http://ops.jlgltech.com/api/cmdb/service/info/all"
SONAR_URL = "http://sonar.jlgltech.com"
logger = logging.getLogger(__name__)


def handle(request: http.HttpRequest):
    data = request.GET
    proj_key = data["proj_key"]
    sonar_result = get_sonar_gate_results_by_app_name(proj_key)
    if sonar_result is not None:
        owner_name = get_cmdb_user(proj_key)
        try:
            lark_open_id = Account.objects.get(name=owner_name).lark_open_id
        except Account.DoesNotExist:
            logging.info(f"{owner_name}已经离职了")
            return http.JsonResponse({"code": 1, "message": f"{owner_name}已经离职了"})
        blocker = sonar_result["blocker"]
        critical = sonar_result["critical"]
        detail_url = sonar_result["sonar_url"]
        message = (
            f"{proj_key}项目的owner：{owner_name}:你好！项目共有{blocker}个blocker级别代码问题，"
            f"{critical}个critical级别代码问题。详情见{detail_url}"
        )
        event = LarkApprovalEvent(open_id=lark_open_id).reply_text(message)
        lark.reply(event)
    return http.JsonResponse({"code": 0})


def get_cmdb_info():
    return requests.get(cmdb_url).json()["data"]


def get_git_name(git_path):
    return git_path.split("/")[-1][0:-4]


def get_cmdb_user(git_name):
    cmdb_list = get_cmdb_info()
    for cmdb_one in cmdb_list:
        cmdb_git_name = get_git_name(cmdb_one["gitpath"])
        if git_name == cmdb_git_name:
            return cmdb_one["owner"]["nickname"]


def get_sonar_gate_results_by_app_name(project_name):
    measure_url = f"{SONAR_URL}/api/measures/search?projectKeys={project_name}" f"&metricKeys=quality_gate_details"
    response_json = requests.get(measure_url).json()
    for measure in response_json.get("measures", []):
        result = {}
        condition_json = json.loads(measure["value"])
        result["app_name"] = measure["component"]
        for condition in condition_json["conditions"]:
            if condition["metric"] == "blocker_violations":
                result["blocker"] = condition["actual"]
            if condition["metric"] == "new_critical_violations":
                result["critical"] = condition["actual"]
        app_name = result["app_name"]
        if int(result["blocker"]) + int(result["critical"]) > 0:
            result[
                "sonar_url"
            ] = f"http://sonar.jlgltech.com/project/issues?id={app_name}&resolved=false&sinceLeakPeriod=true"
            return result
