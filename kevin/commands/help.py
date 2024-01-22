from kevin.core import Kevin
from kevin.events import CommandEvent


@Kevin.command(Kevin("help"))
def show_help(event: CommandEvent):
    keys = "\n/".join(sorted(Kevin.COMMANDS.keys()))
    try:
        return event.reply_text(message=f"以下是目前可以公开的情报：\n/{keys}")
    except Exception as ex:
        return event.error(ex)
