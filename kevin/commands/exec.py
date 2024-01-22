import io
import sys

from kevin.core import Kevin
from kevin.events import CommandEvent


@Kevin.command(Kevin("exec").arg("keyword"))
def exec_python_code(event: CommandEvent):
    """执行python代码"""
    keyword = event.options.keyword
    sys_stdout = sys.stdout
    fake_stdout = io.StringIO()
    sys.stdout = fake_stdout
    try:
        exec(keyword)
        return event.reply_text(fake_stdout.getvalue().strip())
    except Exception as ex:
        return event.error(ex)
    finally:
        sys.stdout = sys_stdout
