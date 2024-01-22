from datetime import datetime

from kevin.core import Kevin
from kevin.endpoints import tasks
from kevin.endpoints.management.models import Account
from kevin.events import CommandEvent


@Kevin.command(Kevin("report", intro="质量月报,日期格式%Y-%m").arg("keyword"))
def quality_monthly_report(event: CommandEvent):
    """ 飞书质量月报 """
    keyword = event.options.keyword
    try:
        now = datetime.strptime(keyword, "%Y-%m")
        user_id = Account.objects.get(lark_open_id=event.open_id).lark_user_id
        docs = tasks.create_doc(user_id, now)
        tasks.create_monthly_report.delay(user_id, docs, keyword)
        return event.reply_text(docs["url"])
    except Exception as ex:
        return event.error(ex)
