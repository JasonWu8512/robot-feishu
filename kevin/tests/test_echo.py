from kevin.tests.utils import KevinTest


class TestEcho(KevinTest):
    def test_echo(self):
        response = self.send_text("/echo hello")
        self.ok(response, message="hello")

    def test_ec(self):
        response = self.send_text("/ec world")
        self.ok(response, message="world")

    def test_e(self):
        response = self.send_text("/e world")
        self.ok(response, type="text")
