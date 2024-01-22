import random
import re

import requests
from django.conf import settings

from kevin.core import Kevin
from kevin.events import CommandEvent


@Kevin.command(Kevin("doutu", intro="搜索表情包").arg("keyword"))
def search_meme(event: CommandEvent):
    """从52doutu网搜表情包"""
    keyword = event.options.keyword
    response = requests.get(f"https://www.52doutu.cn/search/{keyword}/", headers=settings.KEVIN_HEADERS)
    response.raise_for_status()
    images = re.findall(r'href="(https://\w+\.sogoucdn[^"]+)"', response.content.decode())
    if images:
        return event.reply_image(random.choice(images))
    else:
        return event.error("没有找到相关的表情包噢")
