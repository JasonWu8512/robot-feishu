from django.core.management import BaseCommand

from kevin.core import Endpoints
from kevin.events import ReplyTypes


class Command(BaseCommand):
    help = "发送一条消息"

    def add_arguments(self, parser):
        parser.add_argument("words", nargs="*")

    def handle(self, *args, **options):
        text = "/" + " ".join(options["words"])
        event = Endpoints.CMDLINE.handle(text)
        if event.reply_type == ReplyTypes.NO_REPLY:
            return
        if event.reply_type == ReplyTypes.ERROR:
            self.stderr.write(event.reply_message)
        else:
            self.stdout.write(event.reply_message)
