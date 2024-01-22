#! /usr/bin/env bash

celery -A kevin beat -l info --logfile=/home/deploy/log/ace/celery_beat.log --scheduler django_celery_beat.schedulers:DatabaseScheduler
