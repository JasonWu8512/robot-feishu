import time

from kevin.core import Kevin
from kevin.endpoints import lark as _lark
from kevin.endpoints.management.models import Chat
from kevin.events import CommandEvent


@Kevin.command(Kevin("chats"))
def chat_bot(event: CommandEvent):
    """邀请/踢出机器人进群聊"""
    # 等待3秒再去更新群
    time.sleep(3)
    lark = _lark.lark
    chat_list = lark.get_all_chats()
    for chat in chat_list["groups"]:
        Chat.objects.update_or_create(
            chat_id=chat["chat_id"],
            defaults={"description": chat["description"], "name": chat["name"], "owner_user_id": chat["owner_user_id"]},
        )
    return event.reply_text("群聊已更新")
