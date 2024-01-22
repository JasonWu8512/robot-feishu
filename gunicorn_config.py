# -*- coding: utf-8 -*-
# @Time    : 2020/10/21 6:58 下午
# @Author  : zoey
# @File    : gunicorn_config.py
# @Software: PyCharm

bind = "0.0.0.0:8000"
backlog = 2048

workers = 3
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2


spew = False

daemon = False

pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = "/tmp/tmp_upload_dir"

# errorlog = '-'
# loglevel = 'info'
# accesslog = '/var/log/kevin/access.log'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

proc_name = "ace"


def pre_exec(server):
    server.log.info("Forked child, re-executing.")


def when_ready(server):
    server.log.info("Server is ready. Spawning workers")


def worker_abort(worker):
    worker.log.info("worker received SIGABRT signal")
