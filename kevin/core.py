import datetime
import functools
import json
import logging
import os
import pkgutil
import traceback
from argparse import ArgumentParser
from ast import literal_eval

import hutils
from django.conf import settings

from kevin.endpoints.management.models import Account
from kevin.events import BaseEvent, CommandEvent


class Endpoints(hutils.TupleEnum):
    """ 本项目支持的各种输入、输出源 """

    CMDLINE = "cmdline", "命令行"
    DINGTALK = "dingtalk", "钉钉"
    LARK = "lark", "飞书"
    WEBHOOK = "webhook", "HTTP接口"
    WECHAT = "wechat", "微信个人号"

    def handle(self, text: str, username: str = "") -> BaseEvent:
        if not text.startswith("/") or " " not in text:
            return BaseEvent(endpoint=self.value, username=username)
        command_name, text = text[1:].split(None, 1)
        event = CommandEvent(
            endpoint=self.value,
            username=username,
            created_at=datetime.datetime.now(),
            command_name=command_name,
            text=text,
        )
        return self.handle_event(event)

    @classmethod
    def handle_event(cls, event: BaseEvent):
        if not isinstance(event, CommandEvent):
            return event.error("尚未支持的消息类型")
        # 优先取完全匹配，其次取首匹配，最后出 help 信息
        if event.command_name in Kevin.COMMANDS:
            return Kevin.COMMANDS[event.command_name](event)
        commands = [c for c in Kevin.COMMANDS if c.startswith(event.command_name)]
        if len(commands) == 1:
            return Kevin.COMMANDS[commands[0]](event)
        # 匹配是不是机器人自动处理的任务，是完全匹配
        if event.command_name in Bot.COMMANDS:
            return Bot.COMMANDS[event.command_name](event)
        return event.reply_text("目前可以公开的情报：\n/" + "\n/".join(Kevin.COMMANDS.keys()))


class Kevin:
    COMMANDS = {}

    @classmethod
    def command(cls, cmd: "Kevin"):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(event: CommandEvent):
                parser = cmd.parser
                try:
                    if event.text:
                        try:
                            args = [json.dumps(literal_eval(event.text.replace("\n", "\\n")))]
                        except (SyntaxError, ValueError):
                            if "\n" in event.text:
                                prefix, postfix = event.text.split("\n", 1)
                                args = prefix.split() + [postfix]
                            else:
                                args = event.text.split()
                    else:
                        args = []
                    if args and args[0] in ("-h", "--help"):
                        return event.reply_text(parser.format_help())
                    event.options = parser.parse_args(args)
                    return func(event)
                except Account.DoesNotExist:
                    return event.error("我现在还不认识飞书里的你，请稍等，会有人来修的")
                except BaseException as e:
                    logging.exception(traceback.format_exc())
                    return event.error(f"是不是哪里出了问题？\n{parser.format_usage()}\n{e}")

            cls.COMMANDS[cmd.name] = wrapper

            return wrapper

        return decorator

    def __init__(self, name: str, sub="", intro: str = ""):
        self.name = name
        self.sub = sub
        self.intro = intro
        self.parser = ArgumentParser(prog=f"{name} {sub}".strip(), description=f"{name}: {intro}", add_help=False)

    def arg(self, *names: str, **kwargs) -> "Kevin":
        self.parser.add_argument(*names, **kwargs)
        return self


class Bot(Kevin):
    COMMANDS = {}


def load_commands():
    # 机器人shell命令
    commands_directory = os.path.join(settings.BASE_DIR, "kevin/commands")
    for loader, module_name, is_pkg in pkgutil.walk_packages([commands_directory]):
        module = loader.find_module(module_name).load_module(module_name)
        print(Kevin.COMMANDS)
        globals()[module_name] = module
    # 机器人自动处理任务
    commands_directory = os.path.join(settings.BASE_DIR, "kevin/endpoints/management/commands")
    for loader, module_name, is_pkg in pkgutil.walk_packages([commands_directory]):
        module = loader.find_module(module_name).load_module(module_name)
        globals()[module_name] = module


load_commands()
