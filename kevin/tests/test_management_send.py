import io

from django.core.management import call_command

from kevin.tests.utils import KevinTest


class TestManagementSend(KevinTest):
    def test_echo(self):
        stdout = io.StringIO()
        call_command("send", "echo", "hello", stdout=stdout)
        self.assertEqual("hello", stdout.getvalue().strip())
