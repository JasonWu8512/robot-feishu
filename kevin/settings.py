import os
from pathlib import Path

from kevin.config.log_conf import log_conf

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "6!9@xpnf1rrwj(trxv6k15sd2ie8o!+2a&4p&n&x-ngs09dqz-"

# SECURITY WARNING: don't run with debug turned on in production!
IS_PROD = os.getenv("prod", False)
DEBUG = True
if IS_PROD:
    DEBUG = False
    from kevin.config.settings_prod import *  # noqa
else:
    from kevin.config.settings_local import *  # noqa

ALLOWED_HOSTS = ["*"]

# Application definition
INSTALLED_APPS = [
    "simpleui",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_celery_beat",
    "kevin.endpoints",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "kevin.libs.middleware.ApiLoggingMiddleware",
]

ROOT_URLCONF = "kevin.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "kevin.wsgi.application"

# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django_mysql_geventpool.backends.mysql",
        "HOST": "jira.mysql.jlgltech.com",
        "USER": "root",
        "PASSWORD": "123456",
        "PORT": "3306",
        "NAME": "ace",
        "OPTIONS": {"MAX_CONNS": 20, "MAX_LIFETIME": 28790},
    },
    "zero": {
        "ENGINE": "django_mysql_geventpool.backends.mysql",
        "HOST": "jira.mysql.jlgltech.com",
        "USER": "root",
        "PASSWORD": "123456",
        "PORT": "3306",
        "NAME": "zero",
        "OPTIONS": {"MAX_CONNS": 20, "MAX_LIFETIME": 28790},
    },
    # 'default': {
    #     'ENGINE': 'django_mysql_geventpool.backends.mysql',
    #     'HOST': '172.31.112.6',
    #     'USER': 'root',
    #     'PASSWORD': '123456',
    #     'PORT': '3306',
    #     'NAME': 'ace',
    #     'OPTIONS': {'MAX_CONNS': 20, 'MAX_LIFETIME': 28790}
    # },
    # 'zero': {
    #     'ENGINE': 'django_mysql_geventpool.backends.mysql',
    #     'HOST': '172.31.112.6',
    #     'USER': 'root',
    #     'PASSWORD': '123456',
    #     'PORT': '3306',
    #     'NAME': 'zero',
    #     'OPTIONS': {'MAX_CONNS': 20, 'MAX_LIFETIME': 28790}
    # }
}
DATABASE_ROUTERS = ["kevin.database_router.DatabaseAppsRouter"]
DATABASE_APPS_MAPPING = {"kevin.zero": "zero"}

# Logging Settings
if not os.getenv("prod", False):
    LOG_DIR = "/tmp/"
else:
    LOG_DIR = "/home/deploy/log/ace/"

LOGGING = log_conf

# Redis
REDIS_HOST = "localhost"
REDIS_PORT = "6379"
REDIS_PASS = ""
REDIS_URL = os.getenv("REDIS_URL", "redis://:{}@{}:{}/1".format(REDIS_PASS, REDIS_HOST, REDIS_PORT))

# Celery Settings
# Timezone
DJANGO_CELERY_BEAT_TZ_AWARE = False
CELERY_ENABLE_UTC = False
CELERY_TIMEZONE = "Asia/Shanghai"
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_ACKS_LATE = True
# http://docs.celeryproject.org/en/latest/getting-started/brokers/redis.html
CELERY_BROKER_URL = ["redis://:{}@{}:{}/10".format(REDIS_PASS, REDIS_HOST, REDIS_PORT)]

# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Shanghai"

USE_I18N = True

USE_L10N = True

USE_TZ = False

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "static")

# FeiShu Settings
LARK_APP_ID = "cli_a08c2d8ad262900e"
LARK_APP_SECRET = "2JdeQY1j9vj4DUpH8peaNbEfOWbsm4ym"
LARK_VERIFY_TOKEN = "eljAMWnVpflp5FuiaIoV8e7rKsdNFdNs"
LARK_ENCRYPT_KEY = "iKy9xZxux2bPEPjqY34bEd6I3KlDTLAN"

# Zero Settings
ZERO_VERIFY_TOKEN = "zero_jiliguala"

# Kevin Settings
KEVIN_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/86.0.4240.111 Safari/537.36 Kevin"
)
KEVIN_HEADERS = {"User-Agent": KEVIN_USER_AGENT}

# Jira Settings
JIRA_URL = "http://jira.jiliguala.com/"
JIRA_AUTH = ("ace_bot", "Admin!@#$")

# GitLab Settings
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN") or "Ju_34b8bLgXuzRFKqHWT"
GITLAB_URL = "https://gitlab.jiliguala.com"
GITLAB_API_URL = "{}/api/v4/".format(GITLAB_URL)
GITLAB_MR_URL = GITLAB_URL + "/{project}/-/merge_requests/{pr_iid}/diffs?expand_all_diffs=1"
