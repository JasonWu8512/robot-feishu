import os
from datetime import timedelta

import celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kevin.settings")

task_schedule = {
    "kevin.bot.tasks.polling_latest": timedelta(seconds=20),
    "kevin.bot.tasks.refresh_oauth_token": timedelta(minutes=35),
    "kevin.endpoints.lark.sync_lark_users": timedelta(hours=8),
    "kevin.endpoints.management.tasks.fetch_active_courses_status": timedelta(seconds=10),
}
beat_schedule = {task: dict(task=task, schedule=schedule) for task, schedule in task_schedule.items()}
beat_schedule.update(
    {
        "shentong_go_to_work": {
            "task": "kevin.bot.tasks.go_to_work",
            "schedule": crontab(hour=9, minute=30),
            "kwargs": {"room": "【神通】"},
        },
        "dev_go_to_work": {
            "task": "kevin.bot.tasks.go_to_work",
            "schedule": crontab(hour=10, minute=0),
            "kwargs": {"room": "【再惠】技术研究院"},
        },
        "work_report_tip": {
            "task": "kevin.bot.tasks.work_report_tip",
            "schedule": crontab(hour=20, minute=0),
            "kwargs": {"room": "【再惠】到家后端"},
        },
        "make_lunch_orders": {
            "task": "kevin.bot.tasks.make_orders",
            "schedule": crontab(hour=8, minute=15),
            "kwargs": {"meal_type": 1},
        },
        "make_dinner_orders": {
            "task": "kevin.bot.tasks.make_orders",
            "schedule": crontab(hour=13, minute=45),
            "kwargs": {"meal_type": 2},
        },
    },
)

app = celery.Celery("kevin")
app.config_from_object("django.conf:settings", namespace="CELERY")
# app.conf.update(beat_schedule=beat_schedule)
app.autodiscover_tasks()
