# -*- coding: utf-8 -*-
# @Time    : 2020/10/22 10:10 上午
# @Author  : zoey
# @File    : log_conf.py
# @Software: PyCharm
import os

if not os.getenv("prod", False):
    LOG_DIR = "/tmp/"
else:
    LOG_DIR = "/home/deploy/log/ace/"

log_conf = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "standard": {"format": "%(asctime)s FuncName:%(funcName)s LINE:%(lineno)d [%(levelname)s]- %(message)s"},
        "simple": {"format": "%(levelname)s %(message)s"},
        "verbose": {"format": "%(levelname)s %(asctime)s %(module)s %(funcName)s %(message)s"},
    },
    "filters": {"require_debug_false": {"()": "django.utils.log.RequireDebugFalse"}},
    "handlers": {
        "console": {"level": "DEBUG", "class": "logging.StreamHandler", "formatter": "standard"},
        "default_debug": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(LOG_DIR, "debug.log"),
            "maxBytes": 1024 * 1024 * 50,  # 50 MB
            "backupCount": 2,
            "formatter": "standard",
        },
        "request_handler": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(LOG_DIR, "common.log"),
            "maxBytes": 1024 * 1024 * 50,  # 50 MB
            "backupCount": 2,
            "formatter": "standard",
        },
        "restful_api": {
            "level": "DEBUG",
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": os.path.join(LOG_DIR, "api.log"),
            "when": "midnight",
            "interval": 1,
            "backupCount": 30,
            "formatter": "verbose",
        },
        "trace": {
            "level": "DEBUG",
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": os.path.join(LOG_DIR, "trace.log"),
            "when": "midnight",
            "interval": 1,
            "backupCount": 30,
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {"handlers": ["console", "default_debug"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["request_handler"], "level": "INFO", "propagate": False},
        "api": {"handlers": ["restful_api"], "level": "INFO", "propagate": True},
        "trace": {"handlers": ["trace"], "level": "INFO", "propagate": True},
    },
}
