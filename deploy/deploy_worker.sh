#! /usr/bin/env bash

celery worker --app=kevin --loglevel=info --logfile=/home/deploy/log/ace/celery_worker.log
