# Generated by Django 3.1.2 on 2021-04-08 11:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("endpoints", "0013_account_english_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="larkcallback",
            name="ggr_result",
            field=models.CharField(help_text="执行结果", max_length=1023, null=True, verbose_name="执行结果"),
        ),
    ]
