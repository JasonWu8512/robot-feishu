# Generated by Django 3.1.2 on 2021-02-02 14:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("endpoints", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="lark_user_id",
            field=models.CharField(
                editable=False, help_text="飞书 USER_ID", max_length=50, null=True, unique=True, verbose_name="飞书 USER_ID"
            ),
        ),
    ]