# Generated by Django 3.1.2 on 2021-03-25 10:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("endpoints", "0010_chat"),
    ]

    operations = [
        migrations.AddField(
            model_name="larkcallback",
            name="user_name",
            field=models.CharField(help_text="提交人姓名", max_length=50, null=True, verbose_name="提交人姓名"),
        ),
    ]