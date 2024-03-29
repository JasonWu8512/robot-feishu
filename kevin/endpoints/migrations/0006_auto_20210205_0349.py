# Generated by Django 3.1.2 on 2021-02-05 03:49

import datetime
import uuid

import hutils.django.databases
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("endpoints", "0005_auto_20210205_0335"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountGuaId",
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
                (
                    "account_id",
                    models.CharField(editable=False, help_text="用户ID", max_length=50, null=True, verbose_name="用户ID"),
                ),
                (
                    "gua_id",
                    models.CharField(editable=False, help_text="呱ID", max_length=50, null=True, verbose_name="呱ID"),
                ),
            ],
            options={
                "db_table": "ace_account_gua_id",
            },
            bases=(models.Model, hutils.django.databases.ModelMixin),
        ),
        migrations.RemoveField(
            model_name="account",
            name="gua_id",
        ),
    ]
