# Generated by Django 3.1.2 on 2021-03-31 15:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("endpoints", "0012_auto_20210329_1320"),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="role",
            field=models.CharField(help_text="用户类型", max_length=50, null=True),
        ),
    ]