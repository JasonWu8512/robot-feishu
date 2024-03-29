# Generated by Django 3.1.2 on 2021-06-18 15:55

import datetime
import uuid

import hutils.django.databases
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("endpoints", "0023_larkcallback_sublesson_result"),
    ]

    operations = [
        migrations.CreateModel(
            name="StorySubTaskRelation",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uid", models.UUIDField(default=uuid.uuid4, editable=False, help_text="全宇宙唯一身份", unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="上次修改时间")),
                (
                    "deactivated_at",
                    models.DateTimeField(
                        db_index=True,
                        default=datetime.datetime(1970, 1, 1, 0, 0),
                        editable=False,
                        help_text="失效时间（1970年为未失效）",
                    ),
                ),
                ("sub_task", models.CharField(blank=True, help_text="子任务", max_length=50, null=True)),
                ("story", models.CharField(blank=True, help_text="故事", max_length=50, null=True)),
            ],
            options={
                "db_table": "ace_story_subtask_relation",
            },
            bases=(models.Model, hutils.django.databases.ModelMixin),
        ),
    ]
