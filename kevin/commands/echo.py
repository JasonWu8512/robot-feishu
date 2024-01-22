from django import http

from kevin.core import Kevin
from kevin.events import CommandEvent


@Kevin.command(Kevin("echo").arg("keyword", nargs="*"))
def echo(event: CommandEvent):
    """ 回响 """
    if event.text:
        keyword = " ".join(event.options.keyword)
        return event.reply_text(keyword)
    elif event.card:
        return event.reply_card(event.card)
    else:
        return http.JsonResponse({"message": "ok"})
