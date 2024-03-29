# Generated by Django 3.1.2 on 2021-03-16 11:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("endpoints", "0008_larkcallback_result"),
    ]

    operations = [
        migrations.AlterField(
            model_name="account",
            name="default_jira_project",
            field=models.CharField(default="QA", help_text="默认 Jira 项目", max_length=50, verbose_name="默认 Jira 项目"),
        ),
        migrations.AlterField(
            model_name="account",
            name="phone",
            field=models.CharField(blank=True, help_text="手机号", max_length=11, null=True, verbose_name="手机号"),
        ),
    ]
