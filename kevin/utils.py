import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr

import redis
from django.conf import settings


class Redis:
    @classmethod
    def client(cls, db=1, decode=False) -> redis.StrictRedis:
        return redis.StrictRedis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASS,
            db=db,
            socket_timeout=5,
            socket_connect_timeout=5,
            socket_keepalive=True,
            decode_responses=decode,
        )


class SmtpMail:
    @staticmethod
    def send_email(from_addr, password, to_addrs: list, note):
        def _format_addr(s):
            name, addr = parseaddr(s)
            return formataddr((Header(name, "utf-8").encode(), addr))

        smtp_server = "smtp.feishu.cn"
        mail_user = from_addr  # 'zoey_zhang@jiliguala.com'  # 用户名
        mail_pass = password  # "r7nuBZIq5l4qyP38"  # 口令
        message = MIMEText(note, "plain", "utf-8")
        message["From"] = _format_addr(f"ace_bot<{mail_user}>")
        subject = "jira账号自动开通"
        message["Subject"] = Header(subject, "utf-8")
        try:
            smtpObj = smtplib.SMTP()
            smtpObj.connect(smtp_server, 25)  # 25 为 SMTP 端口号
            smtpObj.login(mail_user, mail_pass)
            smtpObj.sendmail(mail_user, to_addrs, message.as_string())
            print("邮件发送成功")
        except Exception as e:
            print("Error: 无法发送邮件")
