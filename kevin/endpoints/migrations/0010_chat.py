# Generated by Django 3.1.2 on 2021-03-17 16:52

import datetime
import uuid

import hutils.django.databases
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("endpoints", "0009_auto_20210316_1146"),
    ]

    operations = [
        migrations.CreateModel(
            name="Chat",
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
                ("chat_id", models.CharField(blank=True, help_text="群聊ID", max_length=50, verbose_name="群聊ID")),
                ("description", models.CharField(blank=True, help_text="群聊描述", max_length=255, verbose_name="群聊描述")),
                ("name", models.CharField(blank=True, help_text="群聊名称", max_length=50, verbose_name="群聊名称")),
                ("owner_user_id", models.CharField(blank=True, help_text="群主ID", max_length=50, verbose_name="群主ID")),
            ],
            options={
                "db_table": "ace_chat",
            },
            bases=(models.Model, hutils.django.databases.ModelMixin),
        ),
    ]
